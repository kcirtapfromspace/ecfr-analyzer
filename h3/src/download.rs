use crate::Result;
use reqwest::blocking::{Client, Response};
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::time::Duration;

const BASE: &str = "https://www.ecfr.gov/api";

fn get(client: &Client, url: &str, gzip: bool) -> Result<Response> {
    let mut error = None;
    // eCFR rate-limits bursts with HTTP 429 and sends no Retry-After, so back off 5..60 s.
    for attempt in 0..6 {
        match client
            .get(url)
            .header("Accept-Encoding", if gzip { "gzip" } else { "identity" })
            .send()
            .and_then(Response::error_for_status)
        {
            Ok(response) => return Ok(response),
            Err(e) => error = Some(e),
        }
        if attempt < 5 {
            std::thread::sleep(Duration::from_secs((5 << attempt).min(60)));
        }
    }
    Err(error.unwrap().into())
}

fn atomic(path: &Path, write: impl FnOnce(&mut File) -> Result<()>) -> Result<()> {
    let temp = path.with_extension(format!("tmp-{}", std::process::id()));
    let result = (|| {
        let mut file = File::create(&temp)?;
        write(&mut file)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temp, path)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(temp);
    }
    result
}

fn cache(client: &Client, path: &Path, url: &str, gzip: bool) -> Result<()> {
    if !path.is_file() {
        atomic(path, |file| {
            std::io::copy(&mut get(client, url, gzip)?, file)?;
            Ok(())
        })?;
    }
    Ok(())
}

// The versions API sends meta counts as strings ("60362"); accept numbers too.
fn number(value: &Value) -> Option<u64> {
    value.as_u64().or_else(|| value.as_str()?.parse().ok())
}

fn versions(client: &Client, path: &Path, title: i64) -> Result<()> {
    if !path.is_file() {
        let url = format!("{BASE}/versioner/v1/versions/title-{title}.json");
        let first: Value = serde_json::from_reader(BufReader::new(get(
            client,
            &format!("{url}?page=1"),
            false,
        )?))?;
        let count = number(&first["meta"]["result_count"]).ok_or("missing result_count")?;
        let pages = number(&first["meta"]["total_pages"]).ok_or("missing total_pages")?;
        let mut rows = first["content_versions"]
            .as_array()
            .ok_or("missing versions")?
            .clone();
        for page in 2..=pages {
            let next: Value = serde_json::from_reader(BufReader::new(get(
                client,
                &format!("{url}?page={page}"),
                false,
            )?))?;
            if number(&next["meta"]["result_count"]) != Some(count) {
                return Err("versions result_count changed during pagination".into());
            }
            rows.extend(
                next["content_versions"]
                    .as_array()
                    .ok_or("missing versions")?
                    .iter()
                    .cloned(),
            );
        }
        if rows.len() as u64 != count {
            return Err(format!(
                "title {title}: expected {count} versions, got {}",
                rows.len()
            )
            .into());
        }
        atomic(path, |file| {
            serde_json::to_writer(
                file,
                &json!({"result_count": count, "content_versions": rows}),
            )?;
            Ok(())
        })?;
    }
    let cached: Value = serde_json::from_reader(BufReader::new(File::open(path)?))?;
    let count = cached["content_versions"]
        .as_array()
        .ok_or("missing cached versions")?
        .len();
    if cached["result_count"].as_u64() != Some(count as u64) {
        return Err(format!("title {title}: cached versions result_count mismatch").into());
    }
    Ok(())
}

pub fn prepare(date: &str, requested: Option<Vec<i64>>) -> Result<(PathBuf, Vec<i64>)> {
    let root = PathBuf::from(format!("data/raw/{date}"));
    fs::create_dir_all(&root)?;
    // Disabling automatic decoding preserves the XML's gzip bytes exactly.
    let client = Client::builder()
        .no_gzip()
        .timeout(Duration::from_secs(120))
        .build()?;
    let titles_path = root.join("titles.json");
    cache(
        &client,
        &titles_path,
        &format!("{BASE}/versioner/v1/titles.json"),
        false,
    )?;
    let listing: Value = serde_json::from_reader(BufReader::new(File::open(titles_path)?))?;
    if listing["meta"]["import_in_progress"]
        .as_bool()
        .ok_or("missing import_in_progress")?
    {
        return Err("eCFR import is in progress".into());
    }
    let available: Vec<i64> = listing["titles"]
        .as_array()
        .ok_or("missing titles")?
        .iter()
        .filter(|t| t["reserved"] == false)
        .map(|t| t["number"].as_i64().ok_or("invalid title number"))
        .collect::<std::result::Result<_, _>>()?;
    let mut titles = requested.unwrap_or_else(|| available.clone());
    titles.sort_unstable();
    titles.dedup();
    if titles.is_empty() || titles.iter().any(|n| !available.contains(n)) {
        return Err("select at least one non-reserved title from titles.json".into());
    }
    cache(
        &client,
        &root.join("agencies.json"),
        &format!("{BASE}/admin/v1/agencies.json"),
        false,
    )?;
    for title in &titles {
        cache(
            &client,
            &root.join(format!("title-{title}.xml.gz")),
            &format!("{BASE}/versioner/v1/full/{date}/title-{title}.xml"),
            true,
        )?;
        versions(
            &client,
            &root.join(format!("versions-{title}.json")),
            *title,
        )?;
    }
    Ok((root, titles))
}
