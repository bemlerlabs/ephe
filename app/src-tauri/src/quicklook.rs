//! N5 — the Quick Look panel, in-process.
//!
//! `qlmanage -p` starts and opens nothing on macOS 26 (measured: one process, zero
//! windows), so the panel comes from `QLPreviewPanel` itself. The class lives in
//! Quartz.framework, which has no objc2 bindings: the framework is loaded and the
//! panel is driven through the runtime, with a data source that answers with the
//! file's URL — `NSURL` already conforms to `QLPreviewItem`.

use std::path::Path;

#[cfg(target_os = "macos")]
mod imp {
    use objc2::rc::Retained;
    use objc2::runtime::{AnyClass, AnyObject, NSObject, NSObjectProtocol};
    use objc2::{define_class, msg_send, AllocAnyThread, DefinedClass};
    use objc2_foundation::{NSBundle, NSString, NSURL};
    use std::path::Path;
    use std::sync::Mutex;

    /// The panel keeps its data source unretained, so the live one is held here
    /// while the panel is on screen. One preview at a time; a second replaces it.
    static SOURCE: Mutex<Option<Retained<Source>>> = Mutex::new(None);

    pub struct SourceIvars {
        url: Retained<NSURL>,
    }

    define_class!(
        #[unsafe(super(NSObject))]
        #[name = "EpheQuickLookSource"]
        #[ivars = SourceIvars]
        pub struct Source;

        unsafe impl NSObjectProtocol for Source {}

        impl Source {
            #[unsafe(method(numberOfPreviewItemsInPreviewPanel:))]
            fn count(&self, _panel: &AnyObject) -> isize {
                1
            }

            #[unsafe(method(previewPanel:previewItemAtIndex:))]
            fn item(&self, _panel: &AnyObject, _index: isize) -> *mut AnyObject {
                self.ivars().url.as_ref() as *const NSURL as *mut AnyObject
            }
        }
    );

    impl Source {
        fn new(url: Retained<NSURL>) -> Retained<Self> {
            let this = Self::alloc().set_ivars(SourceIvars { url });
            unsafe { msg_send![super(this), init] }
        }
    }

    pub fn show(path: &Path) -> Result<(), String> {
        let text = path.to_str().ok_or("path is not valid UTF-8")?;
        unsafe {
            let framework = NSString::from_str("/System/Library/Frameworks/Quartz.framework");
            match NSBundle::bundleWithPath(&framework) {
                Some(bundle) => {
                    bundle.load();
                }
                None => return Err("Quartz framework not found".to_string()),
            }
            let Some(class) = AnyClass::get(c"QLPreviewPanel") else {
                return Err("Quick Look panel class is missing".to_string());
            };
            let panel: *mut AnyObject = msg_send![class, sharedPreviewPanel];
            if panel.is_null() {
                return Err("Quick Look has no shared panel".to_string());
            }

            let url = NSURL::fileURLWithPath(&NSString::from_str(text));
            let source = Source::new(url);
            let source_ptr: *mut AnyObject = Retained::as_ptr(&source) as *mut AnyObject;
            let _: () = msg_send![panel, setDataSource: source_ptr];
            let _: () = msg_send![panel, reloadData];
            let nil: *mut AnyObject = std::ptr::null_mut();
            let _: () = msg_send![panel, makeKeyAndOrderFront: nil];

            if let Ok(mut slot) = SOURCE.lock() {
                *slot = Some(source);
            }
            Ok(())
        }
    }
}

#[cfg(target_os = "macos")]
pub fn show(path: &Path) -> Result<(), String> {
    imp::show(path)
}

#[cfg(not(target_os = "macos"))]
pub fn show(_path: &Path) -> Result<(), String> {
    Err("Quick Look is a macOS feature in this build".to_string())
}
