#[path = "../src/xml.rs"]
mod xml;

use flate2::{write::GzEncoder, Compression};
use sha2::{Digest, Sha256};
use std::io::Write;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

fn parse(source: &str) -> Vec<xml::Part> {
    let path = std::env::temp_dir().join(format!(
        "ecfr-parser-{}-{:?}.xml.gz",
        std::process::id(),
        std::thread::current().id()
    ));
    let mut encoder = GzEncoder::new(std::fs::File::create(&path).unwrap(), Compression::fast());
    encoder.write_all(source.as_bytes()).unwrap();
    encoder.finish().unwrap();
    let mut parts = Vec::new();
    xml::parse(&path, 41, |part| {
        parts.push(part);
        Ok(())
    })
    .unwrap();
    std::fs::remove_file(path).unwrap();
    parts
}

#[test]
fn descendants_tails_entities_and_nearest_ancestors_are_preserved() {
    let parts = parse(
        r#"<ECFR><DIV2 TYPE="SUBTITLE" N="B"><DIV3 TYPE="CHAPTER" N="0">
        <DIV4 TYPE="SUBCHAP" N="A"><DIV5 TYPE="PART" N="1">
        <HEAD>Part <I>One</I> &amp; &#x32;</HEAD><DIV8><HEAD>section heading</HEAD>
        <P>shall<B>must</B>may not, required; prohibited.</P></DIV8>tail</DIV5>
        </DIV4><DIV5 TYPE="PART" N="2"><HEAD>Second</HEAD></DIV5>
        </DIV3></DIV2><DIV5 TYPE="PART" N="3"/></ECFR>"#,
    );
    assert_eq!(parts.len(), 3);
    let first = &parts[0];
    assert_eq!(first.title, 41);
    assert_eq!(first.part, "1");
    assert_eq!(first.subtitle.as_deref(), Some("B"));
    assert_eq!(first.chapter.as_deref(), Some("0"));
    assert_eq!(first.subchapter.as_deref(), Some("A"));
    assert_eq!(first.heading, "Part One & 2");
    assert_eq!(first.ord, 0);
    assert_eq!(first.words, 12);
    assert_eq!(first.restrictions, 5);
    assert_eq!(
        first.hash,
        format!(
            "{:x}",
            Sha256::digest(
                b"Part One & 2 section heading shall must may not, required; prohibited. tail"
            )
        )
    );
    assert_eq!(parts[1].ord, 1);
    assert_eq!(parts[1].subchapter, None);
    assert_eq!(parts[1].words, 1);
    assert_eq!(parts[2].ord, 2);
    assert_eq!(parts[2].heading, "");
    assert_eq!(parts[2].chapter, None);
    assert_eq!(parts[2].words, 0);
}

#[test]
fn comments_cdata_and_processing_instructions_do_not_split_text_nodes() {
    let parts = parse(
        r#"<ECFR><DIV5 TYPE="PART" N="1"><HEAD>e<!-- ignored --><![CDATA[́]]></HEAD>
        <P>sha<!-- ignored -->ll mu<?instruction ignored?>st requ<![CDATA[ired]]></P>
        </DIV5></ECFR>"#,
    );
    assert_eq!(parts[0].heading, "é");
    assert_eq!(parts[0].words, 4);
    assert_eq!(parts[0].restrictions, 3);
    assert_eq!(
        parts[0].hash,
        format!("{:x}", Sha256::digest("é shall must required".as_bytes()))
    );
}

#[test]
fn marks_are_not_part_of_word_runs_and_whitespace_is_canonical() {
    let left = parse("<E><P TYPE=\"PART\" N=\"1\"><HEAD>A</HEAD><X>a̸b ١_2</X></P></E>");
    let right = parse("<E><P TYPE=\"PART\" N=\"1\"><HEAD> A\n </HEAD><X> a̸b\t١_2 </X></P></E>");
    assert_eq!(left[0].words, 5);
    assert_eq!(left[0].hash, right[0].hash);
}

#[test]
fn authority_tags_apply_case_sensitive_rules_in_order() {
    for (note, tag, expected_cites) in [
        ("", "none", vec![]),
        ("<AUTH/>", "none", vec![]),
        (
            "<AUTH>5 U.S.C. 301, 552; Executive Order 1</AUTH>",
            "housekeeping",
            vec!["5 U.S.C. 301"],
        ),
        (
            "<AUTH>5 U.S.C. 301; Public Law 1</AUTH>",
            "statute",
            vec!["5 U.S.C. 301"],
        ),
        ("<AUTH>Pub. L. 1</AUTH>", "statute", vec![]),
        ("<AUTH>E. O. 1</AUTH>", "executive", vec![]),
        ("<AUTH>Executive Order 1</AUTH>", "executive", vec![]),
        ("<AUTH>Proclamation 1</AUTH>", "executive", vec![]),
        ("<AUTH>Reorganization Plan 1</AUTH>", "executive", vec![]),
        ("<AUTH>18 U.S.C. appendix</AUTH>", "other", vec![]),
        (
            "<AUTH>public law; executive order; 5 u.s.c. 301</AUTH>",
            "other",
            vec![],
        ),
        (
            "<AUTH>５ U.S.C. ３０１a</AUTH>",
            "statute",
            vec!["５ U.S.C. ３０１a"],
        ),
        ("<AUTH/><AUTH/>", "other", vec![]),
    ] {
        let source = format!("<E><AUTH>42 U.S.C. 9</AUTH><P TYPE=\"PART\" N=\"1\">{note}</P></E>");
        let parts = parse(&source);
        assert_eq!(parts[0].authority, tag, "{note}");
        assert_eq!(parts[0].cites, expected_cites, "{note}");
    }
}

#[test]
fn all_authority_notes_use_normalized_descendant_text_without_tails() {
    let parts = parse(
        r#"<E><P TYPE="PART" N="1"><AUTH> 5 <I>U. S. C.</I> 301</AUTH>
        <X><AUTH>42 U.S.C 2000e; 42 U.S.C. 2000e; Pub. L. 1</AUTH></X>
        <AUTH>5</AUTH><AUTH>U.S.C. 552</AUTH> 7 U.S.C. 3
        </P><P TYPE="PART" N="2"><AUTH>5 U.S.C. <I>30<!--join--><![CDATA[1]]></I></AUTH></P>
        <P TYPE="PART" N="3"><AUTH>5 U.S.C. <AUTH>301</AUTH></AUTH></P></E>"#,
    );
    assert_eq!(parts[0].authority, "statute");
    assert_eq!(
        parts[0].cites,
        ["42 U.S.C. 2000e", "5 U.S.C. 301", "5 U.S.C. 552"]
    );
    assert_eq!(parts[1].authority, "housekeeping");
    assert_eq!(parts[1].cites, ["5 U.S.C. 301"]);
    assert_eq!(parts[2].authority, "housekeeping");
    assert_eq!(parts[2].cites, ["5 U.S.C. 301"]);
}
