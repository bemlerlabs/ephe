//! The native attachment picker.
//!
//! In the shell the file dialog hands back a path, and the WebView has no file
//! system access, so an attached image used to arrive as a bare name with no
//! bytes: no thumbnail, no lightbox, and nothing for the turn to send. Measured
//! 2026-10-26 on the installed 0.1.8 app.
//!
//! The dialog and the read happen here, in one command. The path never crosses
//! into JavaScript, so a page cannot ask for a file the user did not pick, and
//! every read is capped before it enters the IPC channel.

use std::path::Path;

/// Images are capped well above a screenshot and well below a memory fault.
pub const MAX_IMAGE_BYTES: u64 = 12 * 1024 * 1024;
/// Text follows the browser pipeline's 64 KB prompt cap.
pub const MAX_TEXT_BYTES: usize = 64 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Kind {
    Image(&'static str),
    Text,
    File,
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Attachment {
    pub name: String,
    pub size: u64,
    pub kind: &'static str,
    pub data_url: Option<String>,
    pub text: Option<String>,
    pub truncated: bool,
}

/// The file's role from its extension. No MIME crate: the list is the one the
/// composer and the engine accept, and an unknown extension is a plain file.
pub fn classify(extension: &str) -> Kind {
    match extension.to_ascii_lowercase().as_str() {
        "png" => Kind::Image("image/png"),
        "jpg" | "jpeg" => Kind::Image("image/jpeg"),
        "webp" => Kind::Image("image/webp"),
        "gif" => Kind::Image("image/gif"),
        "heic" => Kind::Image("image/heic"),
        "txt" | "md" | "markdown" | "json" | "toml" | "yml" | "yaml" | "csv" | "log"
        | "py" | "ts" | "tsx" | "js" | "jsx" | "rs" | "go" | "sh" | "zsh" | "html"
        | "css" | "sql" => Kind::Text,
        _ => Kind::File,
    }
}

fn extension_of(path: &Path) -> String {
    path.extension()
        .map(|ext| ext.to_string_lossy().to_string())
        .unwrap_or_default()
}

fn name_of(path: &Path) -> String {
    path.file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| path.to_string_lossy().to_string())
}

/// Standard base64 with padding. Small and fixed, so no dependency is added for
/// one encoding step.
pub fn encode_base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] =
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = *chunk.get(1).unwrap_or(&0) as u32;
        let b2 = *chunk.get(2).unwrap_or(&0) as u32;
        let triple = (b0 << 16) | (b1 << 8) | b2;
        out.push(ALPHABET[((triple >> 18) & 0x3f) as usize] as char);
        out.push(ALPHABET[((triple >> 12) & 0x3f) as usize] as char);
        if chunk.len() > 1 {
            out.push(ALPHABET[((triple >> 6) & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(ALPHABET[(triple & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

/// Read a picked file into the shape the composer consumes.
pub fn read_attachment(path: &Path) -> Result<Attachment, String> {
    let metadata = std::fs::metadata(path).map_err(|err| format!("cannot read the file: {err}"))?;
    if !metadata.is_file() {
        return Err("the pick is not a regular file".into());
    }
    let size = metadata.len();
    let kind = classify(&extension_of(path));
    let name = name_of(path);
    match kind {
        Kind::Image(mime) => {
            if size > MAX_IMAGE_BYTES {
                return Err(format!(
                    "the image is larger than {} MB",
                    MAX_IMAGE_BYTES / (1024 * 1024)
                ));
            }
            let bytes = std::fs::read(path).map_err(|err| format!("cannot read the image: {err}"))?;
            let data_url = format!("data:{mime};base64,{}", encode_base64(&bytes));
            Ok(Attachment {
                name,
                size,
                kind: "image",
                data_url: Some(data_url),
                text: None,
                truncated: false,
            })
        }
        Kind::Text => {
            let bytes = std::fs::read(path).map_err(|err| format!("cannot read the file: {err}"))?;
            let truncated = bytes.len() > MAX_TEXT_BYTES;
            let slice = &bytes[..bytes.len().min(MAX_TEXT_BYTES)];
            Ok(Attachment {
                name,
                size,
                kind: "text",
                data_url: None,
                text: Some(String::from_utf8_lossy(slice).to_string()),
                truncated,
            })
        }
        Kind::File => Ok(Attachment {
            name,
            size,
            kind: "file",
            data_url: None,
            text: None,
            truncated: false,
        }),
    }
}

/// Open the dialog and read what the user picked. `accept` is `image` from the
/// image menu entry and empty from the file entry.
#[cfg(desktop)]
pub fn pick_and_read(
    app: &tauri::AppHandle,
    accept: Option<&str>,
) -> Result<Option<Attachment>, String> {
    use tauri_plugin_dialog::DialogExt;

    let mut builder = app.dialog().file();
    if accept == Some("image") {
        builder = builder.add_filter("Images", &["png", "jpg", "jpeg", "webp", "gif", "heic"]);
    }
    let Some(picked) = builder.blocking_pick_file() else {
        return Ok(None);
    };
    let path = picked
        .into_path()
        .map_err(|err| format!("the dialog returned no path: {err}"))?;
    read_attachment(&path).map(Some)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_extension_decides_the_role() {
        assert_eq!(classify("PNG"), Kind::Image("image/png"));
        assert_eq!(classify("jpeg"), Kind::Image("image/jpeg"));
        assert_eq!(classify("md"), Kind::Text);
        assert_eq!(classify("pdf"), Kind::File);
        assert_eq!(classify(""), Kind::File);
    }

    #[test]
    fn base64_matches_the_rfc_vectors() {
        assert_eq!(encode_base64(b""), "");
        assert_eq!(encode_base64(b"f"), "Zg==");
        assert_eq!(encode_base64(b"fo"), "Zm8=");
        assert_eq!(encode_base64(b"foo"), "Zm9v");
        assert_eq!(encode_base64(b"foob"), "Zm9vYg==");
        assert_eq!(encode_base64(b"fooba"), "Zm9vYmE=");
        assert_eq!(encode_base64(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn an_image_becomes_a_data_url_with_its_name_and_size() {
        let dir = std::env::temp_dir().join(format!("ephe-attach-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("temp dir");
        let file = dir.join("shot.png");
        std::fs::write(&file, [0x89, 0x50, 0x4e, 0x47]).expect("write");
        let attachment = read_attachment(&file).expect("read");
        assert_eq!(attachment.kind, "image");
        assert_eq!(attachment.name, "shot.png");
        assert_eq!(attachment.size, 4);
        assert_eq!(
            attachment.data_url.as_deref(),
            Some("data:image/png;base64,iVBORw==")
        );
        assert_eq!(attachment.text, None);
        let _ = std::fs::remove_file(&file);
    }

    #[test]
    fn a_long_text_file_is_capped_and_says_so() {
        let dir = std::env::temp_dir().join(format!("ephe-attach-text-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("temp dir");
        let file = dir.join("notes.md");
        std::fs::write(&file, "a".repeat(MAX_TEXT_BYTES + 10)).expect("write");
        let attachment = read_attachment(&file).expect("read");
        assert_eq!(attachment.kind, "text");
        assert!(attachment.truncated);
        assert_eq!(attachment.text.as_ref().map(|t| t.len()), Some(MAX_TEXT_BYTES));
        let _ = std::fs::remove_file(&file);
    }

    #[test]
    fn a_missing_file_is_an_error_not_an_empty_attachment() {
        let missing = std::env::temp_dir().join("ephe-attachment-that-does-not-exist.png");
        assert!(read_attachment(&missing).is_err());
    }
}
