#![allow(dead_code)]

include!("../src/main.rs");

struct TestWorkspace {
    original: std::path::PathBuf,
    temporary: std::path::PathBuf,
}

impl Drop for TestWorkspace {
    fn drop(&mut self) {
        env::set_current_dir(&self.original).unwrap();
        fs::remove_dir_all(&self.temporary).unwrap();
    }
}

async fn request_bytes(path: &str) -> (StatusCode, String, Vec<u8>) {
    let response = respond(path.parse().unwrap()).await;
    let status = response.status();
    let content_type = response.headers()[axum::http::header::CONTENT_TYPE]
        .to_str()
        .unwrap()
        .to_string();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap()
        .to_vec();
    (status, content_type, bytes)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn stored_api_responses_html_errors_and_concurrent_reads() {
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .join(STORE);
    assert!(source.is_file(), "run the production ingest first");
    let workspace = TestWorkspace {
        original: env::current_dir().unwrap(),
        temporary: env::temp_dir().join(format!(
            "ecfr-http-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        )),
    };
    fs::create_dir_all(workspace.temporary.join("data/h3")).unwrap();
    fs::create_dir_all(workspace.temporary.join("web")).unwrap();
    fs::copy(source, workspace.temporary.join(STORE)).unwrap();
    let html = "<!doctype html><html><body>Shared eCFR UI — fixture</body></html>";
    fs::write(workspace.temporary.join("web/index.html"), html).unwrap();
    env::set_current_dir(&workspace.temporary).unwrap();

    let db = Connection::open_with_flags(STORE, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let expected: HashMap<String, Value> = db
        .prepare("SELECT path,body FROM response")
        .unwrap()
        .query_map([], |row| {
            let body: String = row.get(1)?;
            Ok((row.get(0)?, serde_json::from_str(&body).unwrap()))
        })
        .unwrap()
        .collect::<rusqlite::Result<_>>()
        .unwrap();
    drop(db);
    let slug = expected["/api/agencies"][0]["slug"].as_str().unwrap();
    let routes = vec![
        "/api/meta".to_string(),
        "/api/agencies".to_string(),
        format!("/api/agencies/{slug}"),
        format!("/api/agencies/{slug}/history"),
    ];
    for path in &routes {
        let (status, content_type, bytes) = request_bytes(path).await;
        assert_eq!(status, StatusCode::OK, "{path}");
        assert_eq!(content_type, "application/json", "{path}");
        assert_eq!(
            serde_json::from_slice::<Value>(&bytes).unwrap(),
            expected[path]
        );
    }
    for path in [
        "/api/agencies/unknown-agency-fixture",
        "/api/agencies/unknown-agency-fixture/history",
    ] {
        let (status, content_type, bytes) = request_bytes(path).await;
        assert_eq!(status, StatusCode::NOT_FOUND, "{path}");
        assert_eq!(content_type, "application/json");
        assert_eq!(bytes, br#"{"detail":"not found"}"#);
    }
    let (status, content_type, bytes) = request_bytes("/").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(content_type, "text/html");
    assert_eq!(bytes, html.as_bytes());

    let expected = std::sync::Arc::new(expected);
    let mut tasks = Vec::new();
    for index in 0..16 {
        let path = routes[index % routes.len()].clone();
        let expected = expected.clone();
        tasks.push(tokio::spawn(async move {
            let (status, content_type, bytes) = request_bytes(&path).await;
            assert_eq!(status, StatusCode::OK);
            assert_eq!(content_type, "application/json");
            assert_eq!(
                serde_json::from_slice::<Value>(&bytes).unwrap(),
                expected[&path]
            );
        }));
    }
    for task in tasks {
        task.await.unwrap();
    }
}
