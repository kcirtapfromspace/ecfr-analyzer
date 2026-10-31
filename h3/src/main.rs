mod download;
mod xml;

use axum::{http::StatusCode, response::IntoResponse, routing::get, Router};
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::HashMap, env, fs, io::BufReader, path::Path};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
const STORE: &str = "data/h3/ecfr.sqlite";
const CUTOFF: &str = "2017-01-01";

const SCHEMA: &str = "
CREATE TABLE part(title INTEGER, part TEXT, subtitle TEXT, chapter TEXT, subchapter TEXT,
 heading TEXT, ord INTEGER, words INTEGER, restrictions INTEGER, hash TEXT,
 authority TEXT, cites_json TEXT,
 PRIMARY KEY(title,part));
CREATE TABLE agency(slug TEXT PRIMARY KEY, name TEXT, short_name TEXT, parent_slug TEXT,
 refs_json TEXT, children_json TEXT);
CREATE TABLE agency_part(slug TEXT, title INTEGER, part TEXT, PRIMARY KEY(slug,title,part));
CREATE INDEX agency_part_membership ON agency_part(title,part);
CREATE TABLE version(title INTEGER, type TEXT, identifier TEXT, date TEXT, part TEXT,
 substantive INTEGER, removed INTEGER);
CREATE UNIQUE INDEX version_key ON version(title,part IS NULL,COALESCE(part,''),type,identifier,date);
CREATE INDEX version_part ON version(title,part);
CREATE TABLE response(path TEXT PRIMARY KEY, body TEXT);";

#[derive(Deserialize)]
struct Event {
    #[serde(rename = "type")]
    kind: String,
    identifier: String,
    date: String,
    part: Option<String>,
    substantive: bool,
    removed: bool,
}

#[derive(Deserialize)]
struct Versions {
    result_count: usize,
    content_versions: Vec<Event>,
}

fn old_checksums() -> Result<HashMap<String, String>> {
    let mut checksums = HashMap::new();
    if Path::new(STORE).exists() {
        let db = Connection::open_with_flags(STORE, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        let body: String = db.query_row(
            "SELECT body FROM response WHERE path='/api/agencies'",
            [],
            |row| row.get(0),
        )?;
        for agency in serde_json::from_str::<Vec<Value>>(&body)? {
            if let Some(checksum) = agency["checksum"].as_str() {
                checksums.insert(agency["slug"].as_str().unwrap().into(), checksum.into());
            }
        }
    }
    Ok(checksums)
}

fn save(db: &Connection, path: &str, body: &Value) -> Result<()> {
    db.execute(
        "INSERT INTO response VALUES (?,?)",
        params![path, body.to_string()],
    )?;
    Ok(())
}

fn children(agency: &Value) -> &[Value] {
    agency["children"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

fn ingest(date: &str, requested: Option<Vec<i64>>) -> Result<()> {
    let started = std::time::Instant::now();
    let (cache, titles) = download::prepare(date, requested)?;
    let previous = old_checksums()?;
    fs::create_dir_all("data/h3")?;
    let temporary = format!("{STORE}.{}.tmp", std::process::id());
    let result = build(&temporary, &cache, date, &titles, &previous);
    if let Err(error) = result {
        let _ = fs::remove_file(&temporary);
        return Err(error);
    }
    fs::rename(&temporary, STORE)?;
    eprintln!(
        "Ingested {titles:?} in {:.3}s; {} bytes",
        started.elapsed().as_secs_f64(),
        fs::metadata(STORE)?.len()
    );
    Ok(())
}

fn build(
    temporary: &str,
    cache: &Path,
    date: &str,
    titles: &[i64],
    previous: &HashMap<String, String>,
) -> Result<()> {
    let mut db = Connection::open(temporary)?;
    db.execute_batch(SCHEMA)?;
    let tx = db.transaction()?;
    for &title in titles {
        let mut insert = tx.prepare("INSERT INTO part VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")?;
        xml::parse(&cache.join(format!("title-{title}.xml.gz")), title, |p| {
            insert.execute(params![
                p.title,
                p.part,
                p.subtitle,
                p.chapter,
                p.subchapter,
                p.heading,
                p.ord,
                p.words,
                p.restrictions,
                p.hash,
                p.authority,
                serde_json::to_string(&p.cites)?
            ])?;
            Ok(())
        })?;
        let versions: Versions = serde_json::from_reader(BufReader::new(fs::File::open(
            cache.join(format!("versions-{title}.json")),
        )?))?;
        if versions.result_count != versions.content_versions.len() {
            return Err(format!("Title {title}: version result_count mismatch").into());
        }
        let mut insert = tx.prepare(
            "INSERT INTO version VALUES (?,?,?,?,?,?,?)
             ON CONFLICT DO UPDATE SET
             substantive=MAX(substantive,excluded.substantive), removed=MAX(removed,excluded.removed)",
        )?;
        for event in versions.content_versions {
            if event.date.as_str() <= date {
                insert.execute(params![
                    title,
                    event.kind,
                    event.identifier,
                    event.date,
                    event.part,
                    event.substantive,
                    event.removed
                ])?;
            }
        }
        let diagnostic: (i64, i64, Option<String>) = tx.query_row(
            "SELECT COUNT(*),COALESCE(SUM(date<?2),0),MAX(CASE WHEN date<?2 THEN date END)
             FROM version WHERE title=?1",
            params![title, CUTOFF],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )?;
        eprintln!(
            "Title {title}: {} baseline / {} rows; latest baseline {:?}",
            diagnostic.1, diagnostic.0, diagnostic.2
        );
    }
    tx.execute_batch(
        "CREATE TEMP TABLE section_counts AS
         SELECT title,part,COUNT(*) AS sections,SUM(date<'2017-01-01') AS stale_sections
         FROM (SELECT title,part,date,removed,ROW_NUMBER() OVER
          (PARTITION BY title,part,type,identifier ORDER BY date DESC) AS latest FROM version)
         WHERE latest=1 AND NOT removed GROUP BY title,part;
         CREATE UNIQUE INDEX section_counts_part ON section_counts(title,part);",
    )?;
    let source: Value =
        serde_json::from_reader(BufReader::new(fs::File::open(cache.join("agencies.json"))?))?;
    let mut agencies = Vec::new();
    for agency in source["agencies"].as_array().ok_or("Missing agencies")? {
        agencies.push((agency, None));
        for child in children(agency) {
            agencies.push((child, agency["slug"].as_str()));
        }
    }
    for (agency, parent) in &agencies {
        let slug = agency["slug"].as_str().ok_or("Missing slug")?;
        let children: Vec<_> = children(agency).iter().map(|a| &a["slug"]).collect();
        tx.execute(
            "INSERT INTO agency VALUES (?,?,?,?,?,?)",
            params![
                slug,
                agency["name"].as_str(),
                agency["short_name"].as_str(),
                parent,
                agency["cfr_references"].to_string(),
                json!(children).to_string()
            ],
        )?;
        for reference in agency["cfr_references"]
            .as_array()
            .ok_or("Missing references")?
        {
            tx.execute(
                "INSERT OR IGNORE INTO agency_part SELECT ?1,title,part FROM part
                 WHERE title=?2 AND (?3 IS NULL OR subtitle=?3) AND (?4 IS NULL OR chapter=?4)
                 AND (?5 IS NULL OR subchapter=?5) AND (?6 IS NULL OR part=?6)",
                params![
                    slug,
                    reference["title"].as_i64(),
                    reference["subtitle"].as_str(),
                    reference["chapter"].as_str(),
                    reference["subchapter"].as_str(),
                    reference["part"].as_str()
                ],
            )?;
        }
    }
    tx.execute(
        "INSERT OR IGNORE INTO agency_part SELECT a.parent_slug,ap.title,ap.part
         FROM agency_part ap JOIN agency a ON a.slug=ap.slug WHERE a.parent_slug IS NOT NULL",
        [],
    )?;
    let mut summaries = Vec::new();
    for (agency, parent) in agencies {
        summaries.push(agency_responses(&tx, agency, parent, previous)?);
    }
    summaries.sort_by(|a, b| {
        b["words"]
            .as_i64()
            .cmp(&a["words"].as_i64())
            .then_with(|| a["slug"].as_str().cmp(&b["slug"].as_str()))
    });
    save(&tx, "/api/agencies", &json!(summaries))?;
    let (parts, words, unattributed): (i64, i64, i64) = tx.query_row(
        "SELECT COUNT(*),COALESCE(SUM(words),0),COALESCE(SUM(CASE WHEN NOT EXISTS
         (SELECT 1 FROM agency_part a WHERE a.title=p.title AND a.part=p.part)
         THEN words ELSE 0 END),0) FROM part p",
        [],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    )?;
    let (baseline, changes, unmatched): (i64, i64, i64) = tx.query_row(
        "SELECT COALESCE(SUM(date<?1),0),COALESCE(SUM(date>=?1),0),
         COALESCE(SUM(date>=?1 AND NOT EXISTS
         (SELECT 1 FROM part p WHERE p.title=v.title AND p.part=v.part)),0) FROM version v",
        [CUTOFF],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    )?;
    let metrics = metrics(&tx, None)?;
    save(
        &tx,
        "/api/meta",
        &json!({"ecfr_date":date,
        "ingested_at":chrono::Utc::now().to_rfc3339(), "titles":titles, "parts":parts,
        "words":words, "unattributed_words":unattributed, "baseline_rows":baseline,
        "change_rows":changes, "unmatched_events":unmatched,
        "sections":metrics["sections"],"stale_sections":metrics["stale_sections"],
        "authority_words":metrics["authority_words"]}),
    )?;
    tx.commit()?;
    db.close().map_err(|(_, error)| error)?;
    Ok(())
}

fn metrics(db: &Connection, slug: Option<&str>) -> Result<Value> {
    let mut authority_words =
        json!({"statute":0,"housekeeping":0,"executive":0,"other":0,"none":0});
    let (mut sections, mut stale_sections) = (0_i64, 0_i64);
    let mut statement = db.prepare(
        "SELECT p.authority,SUM(p.words),COALESCE(SUM(s.sections),0),
         COALESCE(SUM(s.stale_sections),0) FROM part p LEFT JOIN section_counts s USING(title,part)
         WHERE (?1 IS NULL OR EXISTS (SELECT 1 FROM agency_part a
          WHERE a.title=p.title AND a.part=p.part AND a.slug=?1)) GROUP BY p.authority",
    )?;
    let mut rows = statement.query([slug])?;
    while let Some(row) = rows.next()? {
        let authority: String = row.get(0)?;
        authority_words[authority] = json!(row.get::<_, i64>(1)?);
        sections += row.get::<_, i64>(2)?;
        stale_sections += row.get::<_, i64>(3)?;
    }
    Ok(
        json!({"authority_words":authority_words,"sections":sections,"stale_sections":stale_sections,
        "stale_share":if sections == 0 {None} else {Some(stale_sections as f64 / sections as f64)}}),
    )
}

fn agency_responses(
    db: &Connection,
    agency: &Value,
    parent: Option<&str>,
    previous: &HashMap<String, String>,
) -> Result<Value> {
    let slug = agency["slug"].as_str().unwrap();
    let mut statement = db.prepare(
        "SELECT p.title,p.part,p.heading,p.words,p.restrictions,p.hash,p.ord,p.authority,p.cites_json
         FROM part p JOIN agency_part a USING(title,part) WHERE a.slug=? ORDER BY title,ord",
    )?;
    let mut rows = statement.query([slug])?;
    let (mut words, mut restrictions, mut count) = (0_i64, 0_i64, 0_i64);
    let mut digest = Sha256::new();
    let mut top = Vec::new();
    let mut statutes: HashMap<String, (i64, i64)> = HashMap::new();
    while let Some(row) = rows.next()? {
        let (title, part, heading, w, r, hash, ord): (i64, String, String, i64, i64, String, i64) = (
            row.get(0)?,
            row.get(1)?,
            row.get(2)?,
            row.get(3)?,
            row.get(4)?,
            row.get(5)?,
            row.get(6)?,
        );
        let authority: String = row.get(7)?;
        let cites: String = row.get(8)?;
        for cite in serde_json::from_str::<Vec<String>>(&cites)? {
            let totals = statutes.entry(cite).or_default();
            totals.0 += 1;
            totals.1 += w;
        }
        words += w;
        restrictions += r;
        count += 1;
        digest.update(format!("{title}|{part}|{hash}\n"));
        top.push((
            ord,
            json!({"title":title,"part":part,"heading":heading,"words":w,"restrictions":r,"authority":authority}),
        ));
    }
    top.sort_by(|a, b| {
        b.1["words"]
            .as_i64()
            .cmp(&a.1["words"].as_i64())
            .then_with(|| a.1["title"].as_i64().cmp(&b.1["title"].as_i64()))
            .then(a.0.cmp(&b.0))
    });
    let checksum = (count > 0).then(|| format!("{:x}", digest.finalize()));
    let changed = previous
        .get(slug)
        .is_some_and(|old| Some(old) != checksum.as_ref());
    let last: Option<String> = db.query_row(
        "SELECT MAX(v.date) FROM version v JOIN agency_part a USING(title,part) WHERE a.slug=?",
        [slug],
        |row| row.get(0),
    )?;
    let mut summary = json!({"slug":slug,"name":agency["name"],"short_name":agency["short_name"],
        "parent_slug":parent,"words":words,"restrictions":restrictions,"parts":count,
        "density":if words == 0 {None} else {Some(1000.0 * restrictions as f64 / words as f64)},
        "checksum":checksum,"changed":changed,"last_changed":last});
    summary
        .as_object_mut()
        .unwrap()
        .extend(metrics(db, Some(slug))?.as_object().unwrap().clone());
    let mut detail = summary.clone();
    detail["refs"] = agency["cfr_references"].clone();
    detail["children"] = json!(children(agency)
        .iter()
        .map(|a| &a["slug"])
        .collect::<Vec<_>>());
    detail["top_parts"] = json!(top.into_iter().take(10).map(|(_, p)| p).collect::<Vec<_>>());
    let mut statutes: Vec<_> = statutes.into_iter().collect();
    statutes.sort_by(|a, b| b.1 .1.cmp(&a.1 .1).then(a.0.cmp(&b.0)));
    detail["top_statutes"] = json!(statutes
        .into_iter()
        .take(10)
        .map(|(cite, (parts, words))| json!({"cite":cite,"parts":parts,"words":words}))
        .collect::<Vec<_>>());
    save(db, &format!("/api/agencies/{slug}"), &detail)?;
    let mut history = db.prepare(
        "SELECT CAST(substr(date,1,4) AS INTEGER),SUM(NOT removed AND substantive),
         SUM(NOT removed AND NOT substantive),SUM(removed)
         FROM version v JOIN agency_part a USING(title,part)
         WHERE a.slug=?1 AND date>=?2 GROUP BY substr(date,1,4) ORDER BY 1",
    )?;
    let years: Vec<Value> = history
        .query_map(params![slug, CUTOFF], |row| {
            Ok(
                json!({"year":row.get::<_,i64>(0)?,"substantive":row.get::<_,i64>(1)?,
            "nonsubstantive":row.get::<_,i64>(2)?,"removed":row.get::<_,i64>(3)?}),
            )
        })?
        .collect::<rusqlite::Result<_>>()?;
    save(
        db,
        &format!("/api/agencies/{slug}/history"),
        &json!({"slug":slug,"years":years}),
    )?;
    Ok(summary)
}

fn read_response(path: &str) -> Result<Option<String>> {
    let db = Connection::open_with_flags(STORE, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    Ok(db
        .query_row("SELECT body FROM response WHERE path=?", [path], |r| {
            r.get(0)
        })
        .optional()?)
}

async fn respond(uri: axum::http::Uri) -> axum::response::Response {
    let path = uri.path();
    let result = if path == "/" {
        fs::read_to_string("web/index.html")
            .map(Some)
            .map_err(Into::into)
    } else {
        read_response(path)
    };
    let (status, body) = match result {
        Ok(Some(body)) => (StatusCode::OK, body),
        Ok(None) => (
            StatusCode::NOT_FOUND,
            json!({"detail":"not found"}).to_string(),
        ),
        Err(error) => {
            eprintln!("Request {path}: {error}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                json!({"detail":"internal server error"}).to_string(),
            )
        }
    };
    let content_type = if path == "/" && status == StatusCode::OK {
        "text/html"
    } else {
        "application/json"
    };
    (
        status,
        [(axum::http::header::CONTENT_TYPE, content_type)],
        body,
    )
        .into_response()
}

async fn serve(port: u16) -> Result<()> {
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).await?;
    eprintln!("Serving http://127.0.0.1:{port}");
    axum::serve(listener, Router::new().fallback(get(respond))).await?;
    Ok(())
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let command = args
        .next()
        .ok_or("Usage: ecfr ingest --date DATE [--titles N,...] | serve --port N")?;
    let (mut date, mut titles, mut port) = (None, None, 8303);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or("Missing option value")?;
        match (command.as_str(), flag.as_str()) {
            ("ingest", "--date") => {
                chrono::NaiveDate::parse_from_str(&value, "%Y-%m-%d")?;
                date = Some(value);
            }
            ("ingest", "--titles") => {
                titles = Some(
                    value
                        .split(',')
                        .map(str::parse)
                        .collect::<std::result::Result<Vec<i64>, _>>()?,
                )
            }
            ("serve", "--port") => port = value.parse()?,
            _ => return Err(format!("Unknown command or option: {command} {flag}").into()),
        }
    }
    match command.as_str() {
        "ingest" => ingest(&date.ok_or("--date is required")?, titles),
        "serve" => tokio::runtime::Runtime::new()?.block_on(serve(port)),
        _ => Err(format!("Unknown command: {command}").into()),
    }
}
