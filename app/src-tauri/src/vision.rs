//! N7 — text from an image on Apple's Vision framework.
//!
//! `VNRecognizeTextRequest` runs on the Neural Engine: no model download, no
//! tokens, and the text is on disk before any engine sees the picture. The
//! command is called once per attached image; a file that Vision cannot read
//! comes back as a refusal, and an image without text answers with an empty
//! string rather than an error.

use std::path::Path;

/// German first, English second: the two product languages, and Vision treats
/// the list as a preference order rather than a filter.
pub const LANGUAGES: [&str; 2] = ["de-DE", "en-US"];

pub fn extract(path: &Path) -> Result<String, String> {
    let bytes = std::fs::read(path).map_err(|error| format!("image is unreadable: {error}"))?;
    extract_bytes(&bytes)
}

#[cfg(target_os = "macos")]
pub fn extract_bytes(bytes: &[u8]) -> Result<String, String> {
    use objc2::rc::{autoreleasepool, Retained};
    use objc2::AllocAnyThread;
    use objc2::runtime::AnyObject;
    use objc2_foundation::{NSArray, NSData, NSDictionary, NSString};
    use objc2_vision::{
        VNImageBasedRequest, VNImageOption, VNImageRequestHandler, VNRecognizeTextRequest, VNRequest,
        VNRequestTextRecognitionLevel,
    };

    if bytes.is_empty() {
        return Err("image is empty".to_string());
    }

    autoreleasepool(|_pool| {
        let data = NSData::with_bytes(bytes);
        let options = NSDictionary::<VNImageOption, AnyObject>::new();
        let handler =
            VNImageRequestHandler::initWithData_options(VNImageRequestHandler::alloc(), &data, &options);

        let request = VNRecognizeTextRequest::new();
        let languages: Vec<Retained<NSString>> =
            LANGUAGES.iter().map(|code| NSString::from_str(code)).collect();
        request.setRecognitionLanguages(&NSArray::from_retained_slice(&languages));
        request.setRecognitionLevel(VNRequestTextRecognitionLevel::Accurate);

        let image_based: Retained<VNImageBasedRequest> = Retained::into_super(request.clone());
        let generic: Retained<VNRequest> = Retained::into_super(image_based);
        handler
            .performRequests_error(&NSArray::from_retained_slice(&[generic]))
            .map_err(|error| error.localizedDescription().to_string())?;

        let mut lines = Vec::new();
        if let Some(observations) = request.results() {
            for observation in observations.iter() {
                if let Some(best) = observation.topCandidates(1).firstObject() {
                    lines.push(best.string().to_string());
                }
            }
        }
        Ok(lines.join("\n"))
    })
}

#[cfg(not(target_os = "macos"))]
pub fn extract_bytes(_bytes: &[u8]) -> Result<String, String> {
    Err("Vision OCR is a macOS feature in this build".to_string())
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::extract;
    use std::path::{Path, PathBuf};

    fn fixture(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join(name)
    }

    #[test]
    fn reads_the_text_off_a_screenshot() {
        let text = extract(&fixture("ocr-sample.png")).expect("Vision failed");
        assert!(
            text.to_uppercase().contains("EPHE OCR TEST"),
            "Vision returned {text:?}"
        );
    }

    #[test]
    fn an_image_without_text_answers_empty() {
        let text = extract(&fixture("ocr-empty.png")).expect("Vision failed");
        assert!(text.trim().is_empty(), "Vision returned {text:?}");
    }
}
