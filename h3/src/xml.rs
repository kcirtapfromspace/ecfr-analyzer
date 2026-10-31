use flate2::read::GzDecoder;
use quick_xml::{events::Event, Reader};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::{fs::File, io::BufReader, path::Path};
use unicode_normalization::UnicodeNormalization;

#[derive(Debug)]
pub struct Part {
    pub title: i64,
    pub part: String,
    pub subtitle: Option<String>,
    pub chapter: Option<String>,
    pub subchapter: Option<String>,
    pub heading: String,
    pub ord: i64,
    pub words: i64,
    pub restrictions: i64,
    pub hash: String,
    pub authority: String,
    pub cites: Vec<String>,
}

fn normalize(text: &str) -> String {
    text.nfc()
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn flush(
    pending: &mut String,
    text: &mut String,
    heading: &mut String,
    in_head: bool,
    notes: &mut [String],
    auth_stack: &[(usize, usize)],
) {
    if !pending.is_empty() {
        text.push(' ');
        text.push_str(pending);
        if in_head {
            heading.push(' ');
            heading.push_str(pending);
        }
        for &(_, index) in auth_stack {
            notes[index].push(' ');
            notes[index].push_str(pending);
        }
        pending.clear();
    }
}

pub fn parse(
    path: &Path,
    title: i64,
    mut emit: impl FnMut(Part) -> crate::Result<()>,
) -> crate::Result<()> {
    let mut reader = Reader::from_reader(BufReader::new(GzDecoder::new(File::open(path)?)));
    reader.config_mut().expand_empty_elements = true;
    let words = Regex::new(r"[\p{L}\p{N}]+")?;
    let restrictions = Regex::new(r"\b(shall|must|may not|required|prohibited)\b")?;
    let cites = Regex::new(r"(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)")?;
    let public_law = Regex::new(r"Pub\.\s*L\.|Public Law")?;
    let executive = Regex::new(r"E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan")?;
    let mut stack: Vec<(String, Option<String>)> = Vec::new();
    let mut active: Option<(Part, usize)> = None;
    let mut head_depth = None;
    let mut head_seen = false;
    let mut ord = 0;
    let (mut text, mut heading, mut pending) = (String::new(), String::new(), String::new());
    let (mut notes, mut auth_stack) = (Vec::new(), Vec::new());
    let mut buffer = Vec::new();
    loop {
        match reader.read_event_into(&mut buffer)? {
            Event::Start(element) => {
                if active.is_some() {
                    flush(
                        &mut pending,
                        &mut text,
                        &mut heading,
                        head_depth.is_some(),
                        &mut notes,
                        &auth_stack,
                    );
                }
                let (mut kind, mut number) = (String::new(), None);
                for attribute in element.attributes() {
                    let attribute = attribute?;
                    match attribute.key.as_ref() {
                        b"TYPE" => kind = attribute.unescape_value()?.into_owned(),
                        b"N" => number = Some(attribute.unescape_value()?.into_owned()),
                        _ => (),
                    }
                }
                if kind == "PART" {
                    if active.is_some() {
                        return Err("nested PART elements are unsupported".into());
                    }
                    let ancestor = |kind: &str| {
                        stack
                            .iter()
                            .rev()
                            .find(|(candidate, _)| candidate == kind)
                            .and_then(|(_, value)| value.clone())
                    };
                    active = Some((
                        Part {
                            title,
                            part: number.clone().ok_or("PART has no N attribute")?,
                            subtitle: ancestor("SUBTITLE"),
                            chapter: ancestor("CHAPTER"),
                            subchapter: ancestor("SUBCHAP"),
                            heading: String::new(),
                            ord,
                            words: 0,
                            restrictions: 0,
                            hash: String::new(),
                            authority: String::new(),
                            cites: Vec::new(),
                        },
                        stack.len() + 1,
                    ));
                    ord += 1;
                    head_seen = false;
                } else if let Some((_, depth)) = &active {
                    if !head_seen && stack.len() == *depth && element.name().as_ref() == b"HEAD" {
                        head_depth = Some(stack.len() + 1);
                        head_seen = true;
                    }
                }
                if active.is_some() && element.name().as_ref() == b"AUTH" {
                    auth_stack.push((stack.len() + 1, notes.len()));
                    notes.push(String::new());
                }
                stack.push((kind, number));
            }
            Event::Text(value) if active.is_some() => pending.push_str(&value.unescape()?),
            Event::CData(value) if active.is_some() => pending.push_str(&value.decode()?),
            Event::End(_) => {
                if let Some((_, depth)) = &active {
                    flush(
                        &mut pending,
                        &mut text,
                        &mut heading,
                        head_depth.is_some(),
                        &mut notes,
                        &auth_stack,
                    );
                    if stack.len() == *depth {
                        let (mut part, _) = active.take().unwrap();
                        let normalized = normalize(&text);
                        part.heading = normalize(&heading);
                        part.words = words.find_iter(&normalized).count() as i64;
                        part.restrictions =
                            restrictions.find_iter(&normalized.to_lowercase()).count() as i64;
                        part.hash = format!("{:x}", Sha256::digest(normalized.as_bytes()));
                        let authority = notes
                            .iter()
                            .map(|note| normalize(note))
                            .collect::<Vec<_>>()
                            .join(" ");
                        part.cites = cites
                            .captures_iter(&authority)
                            .map(|m| format!("{} U.S.C. {}", &m[1], &m[2]))
                            .collect();
                        part.cites.sort();
                        part.cites.dedup();
                        part.authority = if authority.is_empty() {
                            "none"
                        } else if part.cites.iter().any(|cite| cite != "5 U.S.C. 301")
                            || public_law.is_match(&authority)
                        {
                            "statute"
                        } else if !part.cites.is_empty() {
                            "housekeeping"
                        } else if executive.is_match(&authority) {
                            "executive"
                        } else {
                            "other"
                        }
                        .into();
                        emit(part)?;
                        text.clear();
                        heading.clear();
                        notes.clear();
                    }
                }
                if auth_stack
                    .last()
                    .is_some_and(|&(depth, _)| depth == stack.len())
                {
                    auth_stack.pop();
                }
                if head_depth == Some(stack.len()) {
                    head_depth = None;
                }
                stack.pop();
            }
            Event::Eof => break,
            _ => (),
        }
        buffer.clear();
    }
    if !stack.is_empty() {
        return Err("XML ended before all elements were closed".into());
    }
    Ok(())
}
