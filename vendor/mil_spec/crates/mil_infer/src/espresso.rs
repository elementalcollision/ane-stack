//! `espresso` — execute precompiled ANE programs through `aned`'s
//! deployment path (`_ANEModel` / `_ANEClient` over XPC).
//!
//! This is the loader the OS itself uses for the `.hwx` programs baked
//! into frameworks: a directory holding
//!
//! ```text
//! <name>.espresso.net                  (JSON graph)
//! <name>.espresso.shape                (JSON tensor shapes)
//! <name>.espresso.weights              (weight blob index)
//! <name>.H16.espresso.hwx              (ANE Mach-O — ours, not Apple's)
//! <name>.H16.espresso.precompilation_info
//! ```
//!
//! `_ANEModel modelAtURL:` opens the directory, `aned` takes the
//! precompiled path (`isPreCompiledModel=1`), and evaluation goes
//! through `_ANERequest` objects carrying `_ANEIOSurfaceObject`
//! buffers. No MIL compile, no entitlement — `sharedConnection` is
//! enough.
//!
//! ```text
//! let m = EspressoProgram::load(dir, surface_bytes)?;
//! m.input_mut(0)[..128].copy_from_slice(&fp16_lane_data);
//! m.eval()?;
//! let z = m.output(0);
//! ```
//!
//! Recovered empirically (see `examples/gate0.rs ownexec`): `aned`
//! loads a self-compiled ANE Mach-O and reports its real IO geometry;
//! `evaluateRealTimeWithModel:` then executes it on the engine.

use std::ffi::{c_char, c_void, CString};
use std::path::Path;

extern "C" {
    fn dlopen(path: *const c_char, mode: i32) -> *mut c_void;
    fn dlsym(handle: *mut c_void, name: *const c_char) -> *mut c_void;
}

#[link(name = "objc")]
extern "C" {
    fn objc_getClass(name: *const c_char) -> Id;
    fn sel_registerName(name: *const c_char) -> Sel;
    fn objc_msgSend();
    fn objc_autoreleasePoolPush() -> *mut c_void;
    fn objc_autoreleasePoolPop(pool: *mut c_void);
    fn class_copyMethodList(cls: Id, count: *mut u32) -> *mut *mut c_void;
    fn method_getName(m: *mut c_void) -> Sel;
    fn method_getTypeEncoding(m: *mut c_void) -> *const c_char;
    fn sel_getName(s: Sel) -> *const c_char;
    fn free(p: *mut c_void);
}

#[link(name = "Foundation", kind = "framework")]
extern "C" {
    fn NSSetUncaughtExceptionHandler(f: extern "C" fn(Id));
}

const RTLD_NOW: i32 = 2;
const ANE_FW: &str =
    "/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/AppleNeuralEngine";
const IOSURFACE: &str = "/System/Library/Frameworks/IOSurface.framework/IOSurface";
const FOUNDATION: &str = "/System/Library/Frameworks/Foundation.framework/Foundation";
const COREFOUNDATION: &str = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation";

type Id = *mut c_void;
type Sel = *mut c_void;

/// A decoded `_ANEClient loadModel:` refusal.
///
/// # Where the codes come from
///
/// The NSError description is a selector dump with an opaque code appended:
///
/// ```text
/// loadModel failed: createProgramInstanceForModel:modelToken:…:error::
///     Program load failure (0x170004)
/// ```
///
/// The `0x1X0004` family clusters by **artifact form**, not by who produced
/// the artifact — measured in `docs/evidence/0010-deploy-gate-codes.md`
/// (work item PROBE-2):
///
/// | Code | Form | Seen for |
/// |---|---|---|
/// | `0x170004` | bare Mach-O | our `ANECCompile` output *and* Apple's |
/// | `0x130004` | `.espresso.hwx` bundle | Apple bundles shipped in `/System/Library` |
/// | `0x120004` | `.e5` FlatBuffer bundle | `aned`'s own e5rt cache bundle |
///
/// Those three are the **macOS 26.x** code family. macOS 27.x emits a different
/// message — `Program load failed — bad program image (model may be corrupt or
/// incompatible) (underlying=0x13)` — whose code is nested after `underlying=`.
/// 27.x refusals land on `Unrecognised` with the raw text preserved, because the
/// 27.x *cause text* is not in this table yet.
///
/// Notably `aned`'s *own* output is refused through this path too, so this is
/// not a signature check. PROBE-2 concluded the gate is form-specific and sits
/// in the `_ANEClient` precompiled path — it is neither arch-targeting nor
/// fixable by emitting different bytes. See `docs/adr/0002-deploy-lane-closed.md`.
///
/// # Why this is a heuristic, and says so
///
/// The description is a *raw NSError string* — Apple-private, undocumented,
/// and subject to change. This type decodes the shapes that have actually been
/// observed and falls back to [`AneLoadError::Unrecognised`] rather than
/// guessing. It is deliberately **not** an `#[non_exhaustive]`-free exhaustive
/// claim about the code space; a new code arrives as `Unrecognised` with the
/// raw text preserved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AneLoadError {
    /// The numeric code, when one could be read (`0x170004` → `0x170004`).
    /// Parsed leniently: a leading `-` (NSInteger-wrapped) is accepted.
    pub code: Option<u32>,
    /// What the code means, per the measured table above.
    pub kind: AneLoadKind,
    /// The artifact form inferred from the code, when known. This is what the
    /// code actually discriminates — not the provenance.
    pub form: Option<ArtifactForm>,
    /// The complete NSError description, unmodified. Kept so a new or
    /// unexpected failure is still debuggable.
    pub raw: String,
}

/// What a `loadModel:` refusal means.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AneLoadKind {
    /// `0x170004` — bare Mach-O (`.macho`) rejected.
    BareMachoRejected,
    /// `0x130004` — `.espresso.hwx` bundle rejected.
    EspressoBundleRejected,
    /// `0x120004` — `.e5` FlatBuffer bundle rejected.
    E5BundleRejected,
    /// A code was present but is not in the measured table.
    Unrecognised,
    /// No code could be read from the description at all.
    NoCode,
}

/// Artifact forms, as discriminated by the `0x1X0004` code family.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArtifactForm {
    BareMacho,
    EspressoBundle,
    E5Bundle,
}

impl ArtifactForm {
    /// Infer the form from the path the caller presented.
    ///
    /// Used only to make a suggestion in [`AneLoadError::suggested_cause`];
    /// the authoritative signal is the code, not the path.
    pub fn from_path(path: &std::path::Path) -> Option<Self> {
        let p = path.to_string_lossy();
        if p.contains(".espresso.hwx") || p.ends_with(".hwx") {
            Some(ArtifactForm::EspressoBundle)
        } else if p.ends_with(".e5") || p.contains(".bundle/") {
            Some(ArtifactForm::E5Bundle)
        } else if p.ends_with(".macho") {
            Some(ArtifactForm::BareMacho)
        } else {
            None
        }
    }

    fn from_code(code: u32) -> Option<Self> {
        match code {
            0x170004 => Some(ArtifactForm::BareMacho),
            0x130004 => Some(ArtifactForm::EspressoBundle),
            0x120004 => Some(ArtifactForm::E5Bundle),
            _ => None,
        }
    }
}

impl AneLoadError {
    /// Decode a raw `loadModel:` NSError description.
    ///
    /// Lenient by design — see the type docs on why this must not pretend to
    /// be exhaustive.
    pub fn decode(raw: impl Into<String>) -> Self {
        let raw = raw.into();
        let code = Self::take_code(&raw);
        let (kind, form) = match code {
            Some(c) => {
                let form = ArtifactForm::from_code(c);
                let kind = match form {
                    Some(ArtifactForm::BareMacho) => AneLoadKind::BareMachoRejected,
                    Some(ArtifactForm::EspressoBundle) => AneLoadKind::EspressoBundleRejected,
                    Some(ArtifactForm::E5Bundle) => AneLoadKind::E5BundleRejected,
                    None => AneLoadKind::Unrecognised,
                };
                (kind, form)
            }
            None => (AneLoadKind::NoCode, None),
        };
        Self {
            code,
            kind,
            form,
            raw,
        }
    }

    /// Pull the `0x…` token out of a `loadModel:` description.
    ///
    /// Two message shapes exist, and picking the first `0x` blindly is wrong
    /// for the newer one:
    ///
    /// * macOS 26.x — `…error:: Program load failure (0x170004)`. The code is
    ///   in parentheses at the end, and is the only hex token.
    /// * macOS 27.x — `…error:: Program load failed — bad program image (model
    ///   may be corrupt or incompatible) (underlying=0x13)`. The code is
    ///   introduced by `underlying=` and is the *nested* value.
    ///
    /// So prefer `underlying=0x…` when present (it is unambiguous), then fall
    /// back to a parenthesised `(0x…)`, then to the first hex token. An
    /// unparseable token yields `None` rather than a bogus value.
    ///
    /// Measured on macOS 27.0 with `examples/raw_err_dp.rs`: the naive
    /// first-token rule returned `Some(19)` for `(underlying=0x13)` and
    /// classified a real deploy refusal as `Unrecognised`. Both message shapes
    /// are asserted in tests, because the two shapes are indistinguishable by
    /// inspection without OS-specific provenance.
    fn take_code(raw: &str) -> Option<u32> {
        if let Some(pos) = raw.find("underlying=") {
            // Skip past `underlying=0x` — otherwise take_while starts on `0`
            // and stops at the `x`, yielding a bogus zero.
            let digits: String = raw[pos + "underlying=0x".len()..]
                .chars()
                .take_while(|c| c.is_ascii_hexdigit())
                .collect();
            if !digits.is_empty() {
                return u32::from_str_radix(&digits, 16).ok();
            }
        }
        // Otherwise the code sits in trailing parentheses: `... (0x170004)`.
        // `rfind` so an earlier `(0x…)` in selector text loses to the terminal
        // one. Note the +3: skip past `(0x`, so `take_while` starts on the
        // digits and is not fooled by the `x`.
        if let Some(open) = raw.rfind("(0x") {
            let digits: String = raw[open + 3..]
                .chars()
                .take_while(|c| c.is_ascii_hexdigit())
                .collect();
            if !digits.is_empty() {
                return u32::from_str_radix(&digits, 16).ok();
            }
        }
        let start = raw.find("0x")?;
        let digits: String = raw[start + 2..]
            .chars()
            .take_while(|c| c.is_ascii_hexdigit())
            .collect();
        if digits.is_empty() {
            return None;
        }
        u32::from_str_radix(&digits, 16).ok()
    }

    /// A cause hypothesis for an operator, or `None` when nothing is known.
    ///
    /// Returns `None` for unrecognised codes on purpose: inventing a cause for
    /// a code we have never measured is worse than admitting ignorance.
    pub fn suggested_cause(&self) -> Option<&'static str> {
        match self.kind {
            AneLoadKind::BareMachoRejected => Some(
                "bare Mach-O is refused by the _ANEClient precompiled path. \
                 Not arch-specific: an h17-targeted build fails identically to h16g. \
                 Use the e5rt lane (`milc ane run model.mil`) instead.",
            ),
            AneLoadKind::EspressoBundleRejected => Some(
                "`.espresso.hwx` bundles are refused even when Apple shipped them \
                 (measured on /System/Library artifacts), so this is not a signing check.",
            ),
            AneLoadKind::E5BundleRejected => Some(
                "`aned`'s own `.e5` bundle is refused through this path too. \
                 An e5 bundle is loadable via e5rt (op bind + execute_sync), \
                 not via _ANEClient loadModel.",
            ),
            AneLoadKind::Unrecognised => None,
            AneLoadKind::NoCode => None,
        }
    }

    /// True when the refusal is a known instance of the deploy gate described
    /// in `docs/adr/0002-deploy-lane-closed.md`, rather than a novel failure.
    pub fn is_known_deploy_gate(&self) -> bool {
        self.form.is_some()
    }

    /// The form the caller appeared to present, for diagnostics.
    pub fn presented_form(&self, path: &std::path::Path) -> Option<ArtifactForm> {
        ArtifactForm::from_path(path)
    }
}

impl std::fmt::Display for AneLoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match (self.code, self.kind) {
            (Some(c), AneLoadKind::Unrecognised) => write!(
                f,
                "loadModel refused (unrecognised code 0x{c:06X}): {}",
                self.raw
            ),
            (Some(c), _) => write!(f, "loadModel refused (0x{c:06X}): {}", self.raw),
            (None, _) => write!(f, "loadModel refused (no code): {}", self.raw),
        }
    }
}

#[derive(Debug)]
pub enum EspError {
    FrameworkLoad,
    MissingClass(&'static str),
    MissingSel(&'static str),
    Msg(String),
    /// `loadModel:` was refused by `_ANEClient`. Carries a decoded
    /// [`AneLoadError`] instead of a pre-formatted string, so a caller can
    /// branch on the code rather than grep the message.
    ///
    /// The raw NSError text is retained in `raw` because the decode is
    /// heuristic (see [`AneLoadError::decode`]) and an operator debugging a
    /// *new* code needs the original bytes.
    Load(AneLoadError),
}

impl std::fmt::Display for EspError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EspError::FrameworkLoad => write!(f, "framework dlopen failed"),
            EspError::MissingClass(c) => write!(f, "ObjC class {c} not registered"),
            EspError::MissingSel(s) => write!(f, "symbol {s} failed to resolve"),
            EspError::Msg(s) => write!(f, "{s}"),
            EspError::Load(e) => write!(f, "{e}"),
        }
    }
}
impl std::error::Error for EspError {}

fn cstr(s: &str) -> CString {
    CString::new(s).unwrap()
}

fn selp(name: &str) -> Sel {
    unsafe { sel_registerName(cstr(name).as_ptr()) }
}

/// `objc_msgSend` typed by signature.
macro_rules! msg {
    (($($t:ty),*) -> $r:ty) => {
        std::mem::transmute::<usize, unsafe extern "C" fn(Id, Sel $(, $t)*) -> $r>(
            objc_msgSend as *const () as usize,
        )
    };
}

/// ObjC class handles we drive.
struct Objc {
    ane_model: Id,
    ane_client: Id,
    ane_request: Id,
    ane_surf: Id,
    ns_string: Id,
    ns_url: Id,
    ns_array: Id,
    ns_number: Id,
    ns_dict: Id,
    ns_marr: Id,
    ns_mdata: Id,
}

impl Objc {
    fn open() -> Result<Self, EspError> {
        for fw in [FOUNDATION, IOSURFACE, ANE_FW] {
            if unsafe { dlopen(cstr(fw).as_ptr(), RTLD_NOW) }.is_null() {
                return Err(EspError::FrameworkLoad);
            }
        }
        let cls = |n: &'static str| -> Result<Id, EspError> {
            let c = unsafe { objc_getClass(cstr(n).as_ptr()) };
            if c.is_null() {
                Err(EspError::MissingClass(n))
            } else {
                Ok(c)
            }
        };
        Ok(Objc {
            ane_model: cls("_ANEModel")?,
            ane_client: cls("_ANEClient")?,
            ane_request: cls("_ANERequest")?,
            ane_surf: cls("_ANEIOSurfaceObject")?,
            ns_string: cls("NSString")?,
            ns_url: cls("NSURL")?,
            ns_array: cls("NSArray")?,
            ns_number: cls("NSNumber")?,
            ns_dict: cls("NSDictionary")?,
            ns_marr: cls("NSMutableArray")?,
            ns_mdata: cls("NSMutableData")?,
        })
    }

    fn ns_string(&self, s: &str) -> Id {
        unsafe {
            let f = msg!((Id) -> Id);
            f(
                self.ns_string,
                selp("stringWithUTF8String:"),
                cstr(s).as_ptr() as Id,
            )
        }
    }
    fn ns_url(&self, path: &Path) -> Id {
        unsafe {
            let s = self.ns_string(&path.to_string_lossy());
            let f = msg!((Id) -> Id);
            f(self.ns_url, selp("fileURLWithPath:"), s)
        }
    }
    fn ns_int(&self, v: u64) -> Id {
        unsafe {
            let f = msg!((u64) -> Id);
            f(self.ns_number, selp("numberWithUnsignedLongLong:"), v)
        }
    }
    fn ns_arr(&self, objs: &[Id]) -> Id {
        unsafe {
            let f = msg!((*const Id, usize) -> Id);
            f(
                self.ns_array,
                selp("arrayWithObjects:count:"),
                objs.as_ptr(),
                objs.len(),
            )
        }
    }
    fn empty_dict(&self) -> Id {
        unsafe {
            let f = msg!(() -> Id);
            f(self.ns_dict, selp("dictionary"))
        }
    }

    /// `objectForKey:` on an NSDictionary (returns null for missing keys).
    fn dict_get(&self, dict: Id, key: &str) -> Id {
        if dict.is_null() {
            return std::ptr::null_mut();
        }
        unsafe {
            let k = self.ns_string(key);
            msg!((Id) -> Id)(dict, selp("objectForKey:"), k)
        }
    }

    /// `allKeys` → Vec<String>.
    fn dict_keys(&self, dict: Id) -> Vec<String> {
        if dict.is_null() {
            return vec![];
        }
        unsafe {
            let keys = msg!(() -> Id)(dict, selp("allKeys"));
            let n = msg!(() -> usize)(keys, selp("count"));
            (0..n)
                .map(|i| {
                    let k = msg!((usize) -> Id)(keys, selp("objectAtIndex:"), i);
                    ns_str(k)
                })
                .collect()
        }
    }

    /// `objectAtIndex:` on an NSArray.
    fn arr_at(&self, arr: Id, i: usize) -> Id {
        if arr.is_null() {
            return std::ptr::null_mut();
        }
        unsafe { msg!((usize) -> Id)(arr, selp("objectAtIndex:"), i) }
    }
    fn arr_count(&self, arr: Id) -> usize {
        if arr.is_null() {
            return 0;
        }
        unsafe { msg!(() -> usize)(arr, selp("count")) }
    }
    /// NSNumber → u64.
    fn num(&self, n: Id) -> u64 {
        if n.is_null() {
            return 0;
        }
        unsafe { msg!(() -> u64)(n, selp("unsignedLongLongValue")) }
    }
}

fn retain(o: Id) -> Id {
    unsafe { msg!(() -> Id)(o, selp("retain")) }
}
fn release(o: Id) {
    unsafe { msg!(() -> ())(o, selp("release")) }
}

/// IOSurface/CoreFoundation C entry points via `dlsym`.
struct IoApi {
    get_base: unsafe extern "C" fn(Id) -> *mut c_void,
    alloc_size: unsafe extern "C" fn(Id) -> usize,
    cf_retain: unsafe extern "C" fn(Id) -> Id,
    cf_release: unsafe extern "C" fn(Id),
}

impl IoApi {
    fn open() -> Result<Self, EspError> {
        let hi = unsafe { dlopen(cstr(IOSURFACE).as_ptr(), RTLD_NOW) };
        let hc = unsafe { dlopen(cstr(COREFOUNDATION).as_ptr(), RTLD_NOW) };
        if hi.is_null() || hc.is_null() {
            return Err(EspError::FrameworkLoad);
        }
        let sym = |h: *mut c_void, n: &'static str| -> Result<*mut c_void, EspError> {
            let p = unsafe { dlsym(h, cstr(n).as_ptr()) };
            if p.is_null() {
                Err(EspError::MissingSel(n))
            } else {
                Ok(p)
            }
        };
        Ok(IoApi {
            get_base: unsafe { std::mem::transmute(sym(hi, "IOSurfaceGetBaseAddress")?) },
            alloc_size: unsafe { std::mem::transmute(sym(hi, "IOSurfaceGetAllocSize")?) },
            cf_retain: unsafe { std::mem::transmute(sym(hc, "CFRetain")?) },
            cf_release: unsafe { std::mem::transmute(sym(hc, "CFRelease")?) },
        })
    }
}

/// One IO symbol's layout as `aned` decoded it from the hwx
/// (`NetworkStatusList` entry). Strides are in bytes; element `(b, d,
/// c, h, w)` lands at
/// `b*batch_stride + d*depth_stride + c*plane_stride + h*row_stride + w*elem`.
#[derive(Debug, Clone, Default)]
pub struct TensorDesc {
    /// Symbol name from the package `.net` (`x`, `z@output`, ...).
    pub name: String,
    /// Element type string (`Float16`, ...).
    pub ty: String,
    /// Batches.
    pub n: u64,
    /// Channels (the `k` dimension).
    pub k: u64,
    /// Height.
    pub h: u64,
    /// Width.
    pub w: u64,
    /// Bytes per channel plane.
    pub plane_stride: u64,
    /// Bytes per row.
    pub row_stride: u64,
    /// Bytes per batch.
    pub batch_stride: u64,
    /// Bytes per depth step.
    pub depth_stride: u64,
    /// Element size in bytes (2 for fp16).
    pub elem: u64,
}

impl TensorDesc {
    /// Byte offset of element `(b, c, h, w)` (depth folded into batch
    /// for the flat 4-D case — `d` rides `depth_stride` if present).
    pub fn offset(&self, b: u64, d: u64, c: u64, h: u64, w: u64) -> usize {
        (b * self.batch_stride
            + d * self.depth_stride
            + c * self.plane_stride
            + h * self.row_stride
            + w * self.elem) as usize
    }

    /// Total bytes the IOSurface needs (batches are the outermost dim).
    pub fn bytes(&self) -> usize {
        let span = self
            .batch_stride
            .max(self.depth_stride * self.n.max(1))
            .max(self.plane_stride * self.k.max(1))
            .max(self.row_stride * self.h.max(1))
            .max(self.elem * self.w.max(1));
        (span.max(16384)) as usize
    }
}

/// One program IO buffer: an IOSurface plus its `_ANEIOSurfaceObject`
/// wrapper (what `_ANERequest` wants in its arrays).
/// Latency + I/O profile from [`EspressoProgram::bench`].
#[derive(Debug, Clone)]
pub struct BenchResult {
    pub steps: u32,
    pub min_us: f64,
    pub mean_us: f64,
    pub p99_us: f64,
    pub total_us: f64,
    /// Total bytes across the bound input surfaces.
    pub in_bytes: usize,
    /// Total bytes across the bound output surfaces.
    pub out_bytes: usize,
}

impl BenchResult {
    /// Effective read+write bandwidth at the mean latency, GB/s.
    pub fn gbps(&self) -> f64 {
        (self.in_bytes + self.out_bytes) as f64 / self.mean_us / 1e3
    }
}

pub struct Surface {
    /// Raw `IOSurfaceRef` (+1, released on drop when `owned`).
    surf: Id,
    /// Retained `_ANEIOSurfaceObject`.
    wrap: Id,
    len: usize,
    /// `false` for surfaces created by `alias_*` — they borrow another
    /// port's handle and must not be released on drop.
    owned: bool,
}

/// A runtime-owned IOSurface that outlives any program bound to it —
/// the substrate for lazy program residency: `GraphRuntime` holds one
/// `Rc<SharedSurface>` per tensor edge, adopts it onto producer output
/// and consumer input ports at (re)load time, and may freely unload
/// programs without losing data (persistent KV-cache surfaces included).
pub struct SharedSurface {
    io: IoApi,
    surf: Id,
    len: usize,
}

impl SharedSurface {
    /// Allocate `bytes` of zeroed surface memory.
    pub fn new(bytes: usize) -> Result<Self, EspError> {
        let objc = Objc::open()?;
        let io = IoApi::open()?;
        let surf = unsafe {
            let f = msg!((usize, usize, usize) -> Id);
            f(
                objc.ane_surf,
                selp("createIOSurfaceWithWidth:pixel_size:height:"),
                bytes / 2,
                2,
                1,
            )
        };
        if surf.is_null() {
            return Err(EspError::Msg("createIOSurface failed".into()));
        }
        Ok(Self {
            io,
            surf,
            len: bytes,
        })
    }

    /// Raw `IOSurfaceRef` for `adopt_input` / `adopt_output`.
    pub fn as_ptr(&self) -> *mut c_void {
        self.surf
    }

    /// Read-only view of the surface bytes.
    pub fn bytes(&self) -> &[u8] {
        let p = unsafe { (self.io.get_base)(self.surf) } as *const u8;
        unsafe { std::slice::from_raw_parts(p, self.len) }
    }

    /// Mutable view of the surface bytes.
    pub fn bytes_mut(&self) -> &mut [u8] {
        let p = unsafe { (self.io.get_base)(self.surf) } as *mut u8;
        unsafe { std::slice::from_raw_parts_mut(p, self.len) }
    }
}

impl Drop for SharedSurface {
    fn drop(&mut self) {
        unsafe { (self.io.cf_release)(self.surf) };
    }
}

/// A precompiled Espresso package loaded into `aned`, buffers bound.
pub struct EspressoProgram {
    objc: Objc,
    io: IoApi,
    model: Id,
    client: Id,
    /// Input surfaces in symbol order (`inputSyms` indexes 0..n).
    pub inputs: Vec<Surface>,
    /// Output surfaces in symbol order.
    pub outputs: Vec<Surface>,
    /// Per-symbol input layouts from `NetworkStatusList`.
    pub input_descs: Vec<TensorDesc>,
    /// Per-symbol output layouts.
    pub output_descs: Vec<TensorDesc>,
    /// Procedure name → procedureIndex map
    /// (`kANEFModelProcedureNameToIDMapKey`).
    pub procedures: Vec<(String, u64)>,
    /// `numInputs` / `numOutputs` as `aned` reported from the hwx.
    pub num_inputs: u64,
    pub num_outputs: u64,
    /// `aned`'s program handle.
    pub program_handle: u64,
}

impl EspressoProgram {
    /// Load the package directory through `_ANEClient sharedConnection`
    /// and allocate one IOSurface per IO symbol, sized from the model's
    /// own `NetworkStatusList` descriptors.
    pub fn load(dir: &Path) -> Result<Self, EspError> {
        let pool = unsafe { objc_autoreleasePoolPush() };
        let r = Self::load_inner(dir, false, &[]);
        unsafe { objc_autoreleasePoolPop(pool) };
        r
    }

    /// Load a bare `.hwx`/`.macho` file as a precompiled model:
    /// `modelAtURL:` on the file plus `loadModel` options
    /// `{ANEFModelType: ANEFModelPreCompiled}` — the trigger aned uses
    /// for OS-shipped Espresso packages (found via the
    /// `kANEFModelPreCompiledValue` error path).
    /// `extra`: additional numeric `loadModel` option keys
    /// (`kANEFIntermediateBufferSizeHint`, `kANEFSkipPreparePhaseKey`, ...).
    pub fn load_precompiled(hwx: &Path, extra: &[(&str, u64)]) -> Result<Self, EspError> {
        let pool = unsafe { objc_autoreleasePoolPush() };
        let r = Self::load_inner(hwx, true, extra);
        unsafe { objc_autoreleasePoolPop(pool) };
        r
    }

    /// Parse `modelAttributes` into names, tensor descriptors and the
    /// procedure map.
    fn parse_attrs(
        objc: &Objc,
        model: Id,
    ) -> (Vec<TensorDesc>, Vec<TensorDesc>, Vec<(String, u64)>) {
        unsafe {
            let attrs = msg!((Id) -> Id)(
                model,
                selp("valueForKey:"),
                objc.ns_string("modelAttributes"),
            );
            let mut in_descs = Vec::new();
            let mut out_descs = Vec::new();
            let mut procs = Vec::new();
            if attrs.is_null() {
                return (in_descs, out_descs, procs);
            }
            let parse_list = |key: &str| -> Vec<TensorDesc> {
                let nsl = objc.dict_get(attrs, "NetworkStatusList");
                let first = objc.arr_at(nsl, 0);
                let list = objc.dict_get(first, key);
                let n = objc.arr_count(list);
                (0..n)
                    .map(|i| {
                        let d = objc.arr_at(list, i);
                        let g = |k: &str| objc.num(objc.dict_get(d, k));
                        TensorDesc {
                            name: ns_str(objc.dict_get(d, "Symbol")),
                            ty: ns_str(objc.dict_get(d, "Type")),
                            n: g("Batches"),
                            k: g("Channels"),
                            h: g("Height"),
                            w: g("Width"),
                            plane_stride: g("PlaneStride"),
                            row_stride: g("RowStride"),
                            batch_stride: g("BatchStride"),
                            depth_stride: g("DepthStride"),
                            elem: 2,
                        }
                    })
                    .collect()
            };
            in_descs = parse_list("LiveInputList");
            out_descs = parse_list("LiveOutputList");
            let desc = objc.dict_get(attrs, "ANEFModelDescription");
            let pmap = objc.dict_get(desc, "kANEFModelProcedureNameToIDMapKey");
            for name in objc.dict_keys(pmap) {
                procs.push((name.clone(), objc.num(objc.dict_get(pmap, &name))));
            }
            (in_descs, out_descs, procs)
        }
    }

    fn load_inner(path: &Path, precompiled: bool, extra: &[(&str, u64)]) -> Result<Self, EspError> {
        let objc = Objc::open()?;
        let io = IoApi::open()?;
        unsafe {
            let url = objc.ns_url(path);
            let key = objc.ns_string("probe");
            let model = msg!((Id, Id) -> Id)(objc.ane_model, selp("modelAtURL:key:"), url, key);
            if model.is_null() {
                return Err(EspError::Msg("_ANEModel modelAtURL: returned nil".into()));
            }
            retain(model);
            // Note: `initWithRestrictedAccessAllowed:` produces a
            // client that aned refuses to serve without the
            // restricted-access entitlement — loadModel fails with a
            // bare "unknown". Keep to the shared connection.
            // `ESP_CLIENT=shared|private|new` — the model-load quota is
            // per client connection: `new` gives every program its own
            // client (verified to lift the ~85-model process cap).
            let client = match std::env::var("ESP_CLIENT").as_deref() {
                Ok("private") => msg!(() -> Id)(objc.ane_client, selp("sharedPrivateConnection")),
                Ok("new") => {
                    let a = msg!(() -> Id)(objc.ane_client, selp("alloc"));
                    if a.is_null() {
                        a
                    } else {
                        msg!(() -> Id)(a, selp("init"))
                    }
                }
                _ => msg!(() -> Id)(objc.ane_client, selp("sharedConnection")),
            };
            if client.is_null() {
                release(model);
                return Err(EspError::Msg("_ANEClient connection nil".into()));
            }
            retain(client);
            let opts = if precompiled {
                let mut keys: Vec<Id> = vec![
                    objc.ns_string("kANEFModelType"),
                    // aned's _ANEMachoPatcher transforms the relocatable
                    // Mach-O into the driver-loadable deployed program
                    // only when a non-zero perf-stats mask is present.
                    objc.ns_string("kANEFPerformanceStatsMask"),
                    // Asks the model instance to publish the
                    // procedure→stats-size map + record counters —
                    // the export symbol has a "Key" suffix but the
                    // option string itself does not.
                    objc.ns_string("kANEFModelLoadPerformanceStats"),
                ];
                let mut vals: Vec<Id> = vec![
                    objc.ns_string("kANEFModelPreCompiled"),
                    objc.ns_int(0x7f),
                    objc.ns_int(1),
                ];
                for (k, v) in extra {
                    keys.push(objc.ns_string(k));
                    vals.push(objc.ns_int(*v));
                }
                msg!((*const Id, *const Id, usize) -> Id)(
                    objc.ns_dict,
                    selp("dictionaryWithObjects:forKeys:count:"),
                    vals.as_ptr(),
                    keys.as_ptr(),
                    keys.len(),
                )
            } else {
                objc.empty_dict()
            };
            let mut err: Id = std::ptr::null_mut();
            let f = msg!((Id, Id, u64, *mut Id) -> bool);
            let ok = f(
                client,
                selp("loadModel:options:qos:error:"),
                model,
                opts,
                0,
                &mut err,
            );
            if !ok {
                let msg = err_desc(err);
                release(model);
                release(client);
                // RUN-1: decode the opaque `0x1X0004` family into a typed
                // error instead of handing the caller a string to grep.
                return Err(EspError::Load(AneLoadError::decode(msg)));
            }
            let num_inputs = u64v(model, "numInputs");
            let num_outputs = u64v(model, "numOutputs");
            let program_handle = u64v(model, "programHandle");
            let (input_descs, output_descs, procedures) = Self::parse_attrs(&objc, model);

            let mk = |objc: &Objc, bytes: usize| -> Result<Surface, EspError> {
                let f = msg!((usize, usize, usize) -> Id);
                let surf = f(
                    objc.ane_surf,
                    selp("createIOSurfaceWithWidth:pixel_size:height:"),
                    bytes / 2,
                    2,
                    1,
                );
                if surf.is_null() {
                    return Err(EspError::Msg("createIOSurface failed".into()));
                }
                let wrap = msg!((Id) -> Id)(objc.ane_surf, selp("objectWithIOSurface:"), surf);
                if wrap.is_null() {
                    return Err(EspError::Msg("objectWithIOSurface nil".into()));
                }
                retain(wrap);
                Ok(Surface {
                    surf,
                    wrap,
                    len: bytes,
                    owned: true,
                })
            };
            let mut inputs = Vec::new();
            for i in 0..num_inputs as usize {
                let bytes = input_descs.get(i).map(|d| d.bytes()).unwrap_or(1 << 20);
                inputs.push(mk(&objc, bytes)?);
            }
            let mut outputs = Vec::new();
            for i in 0..num_outputs as usize {
                let bytes = output_descs.get(i).map(|d| d.bytes()).unwrap_or(1 << 20);
                outputs.push(mk(&objc, bytes)?);
            }
            Ok(EspressoProgram {
                objc,
                io,
                model,
                client,
                inputs,
                outputs,
                input_descs,
                output_descs,
                procedures,
                num_inputs,
                num_outputs,
                program_handle,
            })
        }
    }

    fn surf_bytes(&self, s: &Surface) -> (*mut u8, usize) {
        unsafe {
            let base = (self.io.get_base)(s.surf);
            let n = (self.io.alloc_size)(s.surf).min(s.len);
            (base as *mut u8, n)
        }
    }

    /// Raw bytes of input surface `i` (write tensor data in the
    /// program's stride layout before `eval`).
    pub fn input_mut(&mut self, i: usize) -> &mut [u8] {
        let (p, n) = self.surf_bytes(&self.inputs[i]);
        unsafe { std::slice::from_raw_parts_mut(p, n) }
    }

    /// Read-only bytes of input surface `i` — after `eval`, meaningful
    /// for aliased in-place ports.
    pub fn input_bytes(&self, i: usize) -> &[u8] {
        let (p, n) = self.surf_bytes(&self.inputs[i]);
        unsafe { std::slice::from_raw_parts(p, n) }
    }

    /// Alias output `o` onto input `i`'s IOSurface — the program then
    /// reads and writes the same physical pages, giving in-place
    /// persistent state (KV-cache-style) without `state<>` ops.
    /// `Surface` is a pair of retained refs with no `Drop`, so
    /// duplicating the handle is safe.
    pub fn alias_out_to_in(&mut self, o: usize, i: usize) {
        release(self.outputs[o].wrap);
        unsafe { (self.io.cf_release)(self.outputs[o].surf) };
        let s = &self.inputs[i];
        self.outputs[o] = Surface {
            surf: s.surf,
            wrap: s.wrap,
            len: s.len,
            owned: false,
        };
    }

    /// Alias output `o` onto output `i`'s IOSurface — two output descs
    /// write disjoint regions of one shared buffer (e.g. kv_out back
    /// into the cache surface).
    pub fn alias_out_to_out(&mut self, o: usize, i: usize) {
        if o == i {
            return;
        }
        release(self.outputs[o].wrap);
        unsafe { (self.io.cf_release)(self.outputs[o].surf) };
        let s = &self.outputs[i];
        self.outputs[o] = Surface {
            surf: s.surf,
            wrap: s.wrap,
            len: s.len,
            owned: false,
        };
    }

    /// Raw `IOSurfaceRef` of input `i` — opaque handle for
    /// cross-program sharing via [`EspressoProgram::adopt_input`]
    /// / [`EspressoProgram::adopt_output`].
    pub fn input_surf(&self, i: usize) -> *mut c_void {
        self.inputs[i].surf
    }

    /// Raw `IOSurfaceRef` of output `o`.
    pub fn output_surf(&self, o: usize) -> *mut c_void {
        self.outputs[o].surf
    }

    /// Bind input `i` onto a foreign `IOSurfaceRef` (e.g. another
    /// program's output surface, obtained via `output_surf`). The
    /// surface is retained, so either program may drop first.
    pub fn adopt_input(&mut self, i: usize, foreign: *mut c_void) -> Result<(), EspError> {
        Self::adopt(&self.objc, &self.io, &mut self.inputs[i], foreign)
    }

    /// Bind output `o` onto a foreign `IOSurfaceRef`. Same
    /// retain/ownership rules as [`EspressoProgram::adopt_input`].
    pub fn adopt_output(&mut self, o: usize, foreign: *mut c_void) -> Result<(), EspError> {
        Self::adopt(&self.objc, &self.io, &mut self.outputs[o], foreign)
    }

    fn adopt(objc: &Objc, io: &IoApi, slot: &mut Surface, foreign: Id) -> Result<(), EspError> {
        unsafe { (io.cf_retain)(foreign) };
        let wrap =
            unsafe { msg!((Id) -> Id)(objc.ane_surf, selp("objectWithIOSurface:"), foreign) };
        if wrap.is_null() {
            unsafe { (io.cf_release)(foreign) };
            return Err(EspError::Msg("objectWithIOSurface nil".into()));
        }
        retain(wrap);
        if slot.owned {
            release(slot.wrap);
            unsafe { (io.cf_release)(slot.surf) };
        }
        *slot = Surface {
            surf: foreign,
            wrap,
            len: slot.len,
            owned: true,
        };
        Ok(())
    }

    /// Raw bytes of output surface `i` after `eval`.
    pub fn output(&self, i: usize) -> &[u8] {
        let (p, n) = self.surf_bytes(&self.outputs[i]);
        unsafe { std::slice::from_raw_parts(p, n) }
    }

    /// Surface index of input symbol `name` (`x`, `c`, ...).
    pub fn input_named(&self, name: &str) -> Option<usize> {
        self.input_descs.iter().position(|d| d.name == name)
    }

    /// Surface index of output symbol `name`.
    pub fn output_named(&self, name: &str) -> Option<usize> {
        self.output_descs.iter().position(|d| d.name == name)
    }

    /// Evaluate procedure index `proc` (0 = first procedure; see
    /// [`EspressoProgram::procedures`]).
    pub fn eval_proc(&self, proc: u64) -> Result<(), EspError> {
        let pool = unsafe { objc_autoreleasePoolPush() };
        let r = self.eval_inner(proc);
        unsafe { objc_autoreleasePoolPop(pool) };
        r
    }

    /// Evaluate proc 0 with a caller-supplied `weightsBuffer:` — the
    /// request-level weight override slot. The buffer is a raw
    /// `IOSurfaceRef` wrapped like any bound surface. Returns the
    /// daemon's verdict; whether it *honors* the buffer is the probe.
    pub fn eval_wb(&self, weights_surf: *mut c_void) -> Result<(), EspError> {
        let pool = unsafe { objc_autoreleasePoolPush() };
        let r = unsafe {
            let wrap = msg!((Id) -> Id)(
                self.objc.ane_surf,
                selp("objectWithIOSurface:"),
                weights_surf,
            );
            if wrap.is_null() {
                return Err(EspError::Msg("weightsBuffer wrap nil".into()));
            }
            retain(wrap);
            let in_objs: Vec<Id> = self.inputs.iter().map(|s| s.wrap).collect();
            let out_objs: Vec<Id> = self.outputs.iter().map(|s| s.wrap).collect();
            let in_idx: Vec<Id> = (0..self.inputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let out_idx: Vec<Id> = (0..self.outputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let proc_idx = self.objc.ns_int(0);
            let ins = self.objc.ns_arr(&in_objs);
            let ins_i = self.objc.ns_arr(&in_idx);
            let outs = self.objc.ns_arr(&out_objs);
            let outs_i = self.objc.ns_arr(&out_idx);
            let req0 = msg!(() -> Id)(self.objc.ane_request, selp("alloc"));
            let req = msg!((Id, Id, Id, Id, Id, Id, Id, Id, Id) -> Id)(
                req0,
                selp("initWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:sharedEvents:transactionHandle:"),
                ins,
                ins_i,
                outs,
                outs_i,
                wrap,
                std::ptr::null_mut::<c_void>() as Id,
                proc_idx,
                std::ptr::null_mut::<c_void>() as Id,
                std::ptr::null_mut::<c_void>() as Id,
            );
            if req.is_null() {
                return Err(EspError::Msg("wb request init failed".into()));
            }
            let opts = self.objc.empty_dict();
            let mut err: Id = std::ptr::null_mut();
            let ok = msg!((Id, Id, Id, *mut Id) -> bool)(
                self.client,
                selp("evaluateRealTimeWithModel:options:request:error:"),
                self.model,
                opts,
                req,
                &mut err,
            );
            release(wrap);
            if ok {
                Ok(())
            } else {
                Err(EspError::Msg(format!("eval_wb failed: {}", err_desc(err))))
            }
        };
        unsafe { objc_autoreleasePoolPop(pool) };
        r
    }

    /// Evaluate the first procedure.
    pub fn eval(&self) -> Result<(), EspError> {
        self.eval_proc(0)
    }

    /// Submit→complete latency profile over `steps` evals of `proc`.
    /// Wall-clock around the XPC round trip — the same end-to-end
    /// number any external caller sees. `*_bps` figures come from the
    /// bound surface extents, not counters.
    pub fn bench(&self, proc: u64, steps: u32) -> Result<BenchResult, EspError> {
        let mut us = Vec::with_capacity(steps as usize);
        // Warmup — first eval pays map/program-start costs.
        self.eval_proc(proc)?;
        for _ in 0..steps {
            let t = std::time::Instant::now();
            self.eval_proc(proc)?;
            us.push(t.elapsed().as_secs_f64() * 1e6);
        }
        us.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let n = us.len();
        if n == 0 {
            return Err(EspError::Msg("bench: steps=0".into()));
        }
        let in_bytes: usize = self.inputs.iter().map(|s| s.len).sum();
        let out_bytes: usize = self.outputs.iter().map(|s| s.len).sum();
        let total: f64 = us.iter().sum();
        Ok(BenchResult {
            steps: n as u32,
            min_us: us[0],
            mean_us: total / n as f64,
            p99_us: us[(n * 99 / 100).min(n - 1)],
            total_us: total,
            in_bytes,
            out_bytes,
        })
    }

    /// `kANEFModelProcedureNameToStatsSizeMapKey` lives in the model's
    /// `ANEFModelDescription` dict — procedure name → the stats
    /// buffer size the request must carry for that procedure.
    fn model_stats_size(&self) -> usize {
        unsafe {
            let attrs = msg!((Id) -> Id)(
                self.model,
                selp("valueForKey:"),
                self.objc.ns_string("modelAttributes"),
            );
            let desc = self.objc.dict_get(attrs, "ANEFModelDescription");
            for k in self.objc.dict_keys(desc) {
                eprintln!("[perf] modelDescription key: {k}");
            }
            // procedureInfo may carry the per-procedure stats contract
            // (buffer size, mask) even when the description omits it.
            for i in 0..self.procedures.len().min(4) {
                let info = msg!((Id) -> Id)(
                    self.model,
                    selp("procedureInfoForProcedureIndex:"),
                    self.objc.ns_int(i as u64),
                );
                if !info.is_null() {
                    let d = msg!(() -> Id)(info, selp("description"));
                    let mut s = ns_str(d);
                    if s.len() > 1500 {
                        s.truncate(1500);
                        s.push('…');
                    }
                    eprintln!("[perf] procedureInfo[{i}] = {s}");
                }
            }
            let m = self
                .objc
                .dict_get(desc, "kANEFModelProcedureNameToStatsSizeMapKey");
            if m.is_null() {
                return 0;
            }
            let d = msg!(() -> Id)(m, selp("description"));
            eprintln!("[perf] statsSizeMap = {}", ns_str(d));
            // Dict of procedure name -> required buffer size; take the
            // largest so one buffer serves every procedure.
            let mut max = 0usize;
            for k in self.objc.dict_keys(m) {
                let v = msg!((Id) -> Id)(m, selp("objectForKey:"), self.objc.ns_string(&k));
                if !v.is_null() {
                    let n = msg!(() -> u64)(v, selp("unsignedLongLongValue"));
                    max = max.max(n as usize);
                }
            }
            max
        }
    }

    /// Build a `_ANERequest` through the long-form init that carries a
    /// `perfStats` container — the lane the driver fills counters into.
    fn make_request_stats(&self, proc: u64) -> Result<Id, EspError> {
        unsafe {
            let in_objs: Vec<Id> = self.inputs.iter().map(|s| s.wrap).collect();
            let out_objs: Vec<Id> = self.outputs.iter().map(|s| s.wrap).collect();
            let in_idx: Vec<Id> = (0..self.inputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let out_idx: Vec<Id> = (0..self.outputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let proc_idx = self.objc.ns_int(proc);
            let ins = self.objc.ns_arr(&in_objs);
            let ins_i = self.objc.ns_arr(&in_idx);
            let outs = self.objc.ns_arr(&out_objs);
            let outs_i = self.objc.ns_arr(&out_idx);
            // `_ANEPerformanceStatsIOSurface` wraps a caller-allocated
            // IOSurface; the driver fills it with counters during eval.
            // No stats-size map in this model's description — use a
            // generous buffer and let the daemon write what it has.
            let want = match self.model_stats_size() {
                0 => {
                    eprintln!("[perf] no stats-size map — 1MB guess");
                    1 << 20
                }
                n => n,
            };
            // `initWithRequestPerformanceBuffer:statsBufferSize:` takes
            // ^^v / ^I — caller-provided raw buffer + its size. The
            // stats object wraps the region the driver fills.
            let stats_cls = objc_getClass(cstr("_ANEPerformanceStats").as_ptr());
            if stats_cls.is_null() {
                return Err(EspError::MissingClass("_ANEPerformanceStats"));
            }
            let surf = msg!((usize, usize, usize) -> Id)(
                self.objc.ane_surf,
                selp("createIOSurfaceWithWidth:pixel_size:height:"),
                want / 2,
                2usize,
                1usize,
            );
            if surf.is_null() {
                return Err(EspError::Msg("perf-surface alloc failed".into()));
            }
            // The "request performance buffer" is the IOSurface itself —
            // *buf points at the surface ref, *size at its extent.
            let mut perf_buf: *mut c_void = surf;
            let mut perf_size: u32 = want as u32;
            if std::env::var_os("ESP_PROBE_STAGE").is_some() {
                eprintln!("[stage] surf={surf:?} size={want} -> stats factory");
            }
            let stats = msg!((*mut *mut c_void, *mut u32) -> Id)(
                stats_cls,
                selp("statsWithRequestPerformanceBuffer:statsBufferSize:"),
                &mut perf_buf,
                &mut perf_size,
            );
            if std::env::var_os("ESP_PROBE_STAGE").is_some() {
                eprintln!("[stage] stats={stats:?} buf={perf_buf:?} size={perf_size}");
            }
            if stats.is_null() {
                return Err(EspError::Msg("_ANEPerformanceStats factory nil".into()));
            }
            // `perfStats:` takes an NSArray of stats objects — the
            // request exposes it as `perfStatsArray` downstream.
            let arr = [stats];
            let perf_arg = self.objc.ns_arr(&arr);
            if std::env::var_os("ESP_PROBE_STAGE").is_some() {
                eprintln!("[stage] req init: arg={perf_arg:?}");
            }
            let req0 = msg!(() -> Id)(self.objc.ane_request, selp("alloc"));
            let req = msg!((Id, Id, Id, Id, Id, Id, Id, Id, Id) -> Id)(
                req0,
                selp("initWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:sharedEvents:transactionHandle:"),
                ins,
                ins_i,
                outs,
                outs_i,
                std::ptr::null_mut::<c_void>() as Id,
                perf_arg,
                proc_idx,
                std::ptr::null_mut::<c_void>() as Id,
                std::ptr::null_mut::<c_void>() as Id,
            );
            if std::env::var_os("ESP_PROBE_STAGE").is_some() {
                eprintln!("[stage] req={req:?}");
            }
            if req.is_null() {
                return Err(EspError::Msg(
                    "_ANERequest initWith:perfStats: failed".into(),
                ));
            }
            Ok(req)
        }
    }

    /// Build the `_ANERequest` for `proc` (the same object eval uses)
    /// so callers can inspect it after an evaluation.
    fn make_request(&self, proc: u64) -> Result<Id, EspError> {
        unsafe {
            let in_objs: Vec<Id> = self.inputs.iter().map(|s| s.wrap).collect();
            let out_objs: Vec<Id> = self.outputs.iter().map(|s| s.wrap).collect();
            let in_idx: Vec<Id> = (0..self.inputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let out_idx: Vec<Id> = (0..self.outputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let proc_idx = self.objc.ns_int(proc);
            let ins = self.objc.ns_arr(&in_objs);
            let ins_i = self.objc.ns_arr(&in_idx);
            let outs = self.objc.ns_arr(&out_objs);
            let outs_i = self.objc.ns_arr(&out_idx);
            let req = msg!((Id, Id, Id, Id, Id) -> Id)(
                self.objc.ane_request,
                selp("requestWithInputs:inputIndices:outputs:outputIndices:procedureIndex:"),
                ins,
                ins_i,
                outs,
                outs_i,
                proc_idx,
            );
            if req.is_null() {
                return Err(EspError::Msg("_ANERequest init failed".into()));
            }
            Ok(req)
        }
    }

    /// Evaluate `req` through `evaluateRealTimeWithModel:`, requesting
    /// performance stats at the same mask used at load.
    fn eval_request(&self, req: Id) -> Result<(), EspError> {
        unsafe {
            let st = std::env::var_os("ESP_PROBE_STAGE").is_some();
            if st {
                eprintln!("[stage] validate (skipped — throws on stats reqs)");
            }
            let keys = [self.objc.ns_string("kANEFPerformanceStatsMask")];
            let vals = [self.objc.ns_int(0x7f)];
            let opts = msg!((*const Id, *const Id, usize) -> Id)(
                self.objc.ns_dict,
                selp("dictionaryWithObjects:forKeys:count:"),
                vals.as_ptr(),
                keys.as_ptr(),
                1,
            );
            let mut err: Id = std::ptr::null_mut();
            if st {
                eprintln!("[stage] evaluate");
            }
            // Stats profiling rides the non-realtime eval path —
            // realtime eval validates strictly and throws on the
            // stats buffer.
            let ok = msg!((Id, Id, Id, u64, *mut Id) -> bool)(
                self.client,
                selp("evaluateWithModel:options:request:qos:error:"),
                self.model,
                opts,
                req,
                0u64,
                &mut err,
            );
            if st {
                eprintln!("[stage] evaluate -> {ok} err={}", err_desc(err));
            }
            if ok {
                Ok(())
            } else {
                Err(EspError::Msg(format!("evaluate failed: {}", err_desc(err))))
            }
        }
    }

    /// Send a session hint (`ANEHintClientSession*` constant objects,
    /// resolved via `dlsym` on the framework's `kANEFHint*` globals)
    /// and return the report dict the daemon fills in — currently
    /// `ANEClientSessionStatus` / `ANEClientTotalPages` /
    /// `ANEClientResidentPages` for the keys we request. Verified
    /// working: wraps evals in Start/Stop pairs, daemon reports
    /// memory residency back into our mutable dict.
    pub fn session_hint(
        &self,
        hint_symbol: &str,
        want: &[&str],
    ) -> Result<Vec<(String, String)>, EspError> {
        unsafe {
            let (obj, _) = self
                .ksym(hint_symbol)
                .ok_or_else(|| EspError::Msg(format!("no {hint_symbol} export")))?;
            let keys: Vec<Id> = want.iter().map(|k| self.objc.ns_string(k)).collect();
            let vals: Vec<Id> = want.iter().map(|_| self.objc.ns_int(1)).collect();
            let opts = msg!((*const Id, *const Id, usize) -> Id)(
                self.objc.ns_dict,
                selp("dictionaryWithObjects:forKeys:count:"),
                vals.as_ptr(),
                keys.as_ptr(),
                keys.len(),
            );
            let mdict_cls = objc_getClass(cstr("NSMutableDictionary").as_ptr());
            let report = msg!(() -> Id)(mdict_cls, selp("dictionary"));
            let mut err: Id = std::ptr::null_mut();
            let ok = msg!((Id, Id, Id, Id, *mut Id) -> bool)(
                self.client,
                selp("sessionHintWithModel:hint:options:report:error:"),
                self.model,
                obj,
                opts,
                report,
                &mut err,
            );
            if !ok {
                return Err(EspError::Msg(format!(
                    "sessionHint {hint_symbol} failed: {}",
                    err_desc(err)
                )));
            }
            let mut out = Vec::new();
            for k in self.objc.dict_keys(report) {
                let v = msg!((Id) -> Id)(report, selp("objectForKey:"), self.objc.ns_string(&k));
                let d = if v.is_null() {
                    String::new()
                } else {
                    ns_str(msg!(() -> Id)(v, selp("description")))
                };
                out.push((k, d));
            }
            Ok(out)
        }
    }

    /// Probe where `kANEFPerformanceStatsMask = 0x7f` lands the stats:
    /// evaluates once, then sweeps candidate `valueForKey:` /
    /// `respondsToSelector:` entries on the model, the client, and the
    /// post-eval `_ANERequest`. Returns `(target, name, description)`
    /// triples for everything that responded.
    pub fn perf_probe(&self) -> Result<Vec<(String, String, String)>, EspError> {
        let pool = unsafe { objc_autoreleasePoolPush() };
        let r = self.perf_probe_inner();
        unsafe { objc_autoreleasePoolPop(pool) };
        r
    }

    /// List every Objective-C method registered on `cls` (instance
    /// methods). Class objects are passed to the runtime directly.
    pub fn class_methods(cls: Id) -> Vec<String> {
        unsafe {
            let mut n: u32 = 0;
            let list = class_copyMethodList(cls, &mut n);
            let mut out = Vec::new();
            if !list.is_null() {
                let want_enc = std::env::var_os("ANE_DUMP_ENC").is_some();
                for i in 0..n as usize {
                    let m = *list.add(i);
                    let s = method_getName(m);
                    let p = sel_getName(s);
                    if !p.is_null() {
                        let mut name = std::ffi::CStr::from_ptr(p).to_string_lossy().into_owned();
                        if want_enc {
                            let e = method_getTypeEncoding(m);
                            if !e.is_null() {
                                name.push_str(&format!(
                                    "    enc: {}",
                                    std::ffi::CStr::from_ptr(e).to_string_lossy()
                                ));
                            }
                        }
                        out.push(name);
                    }
                }
                free(list as *mut c_void);
            }
            out
        }
    }

    /// Method inventory for the private classes this runtime drives —
    /// `_ANEModel`, `_ANEClient`, `_ANERequest` (instance methods) —
    /// used for API-surface discovery (e.g. hunting the perf-stats
    /// selectors the property probe can't name).
    pub fn method_inventory(&self) -> Vec<(String, Vec<String>)> {
        let mut out = vec![
            ("_ANEModel".into(), Self::class_methods(self.objc.ane_model)),
            (
                "_ANEClient".into(),
                Self::class_methods(self.objc.ane_client),
            ),
            (
                "_ANERequest".into(),
                Self::class_methods(self.objc.ane_request),
            ),
        ];
        unsafe {
            for name in [
                "_ANEPerformanceStats",
                "_ANEPerformanceStatsIOSurface",
                "_ANEDataReporter",
                "_ANESharedEvents",
                "_ANEChainingRequest",
            ] {
                let cls = objc_getClass(cstr(name).as_ptr());
                if !cls.is_null() {
                    // Instance methods live on the class; class methods
                    // (the statsWith… factories) live on the metaclass.
                    let meta: Id = msg!(() -> Id)(cls, selp("class"));
                    out.push((format!("{name} [class]"), Self::class_methods(meta)));
                    out.push((name.into(), Self::class_methods(cls)));
                }
            }
        }
        out
    }

    /// Resolve an exported `kANE*` data symbol to its CF/ObjC object
    /// (the globals are `CFStringRef`s — symbol names ≠ string values).
    fn ksym(&self, name: &str) -> Option<(Id, String)> {
        unsafe {
            let h = dlopen(cstr(ANE_FW).as_ptr(), RTLD_NOW);
            if h.is_null() {
                return None;
            }
            let p = dlsym(h, cstr(name).as_ptr());
            if p.is_null() {
                return None;
            }
            let obj = *(p as *const Id);
            if obj.is_null() {
                return None;
            }
            let d = msg!(() -> Id)(obj, selp("description"));
            Some((obj, ns_str(d)))
        }
    }

    fn perf_probe_inner(&self) -> Result<Vec<(String, String, String)>, EspError> {
        extern "C" fn on_exc(e: Id) {
            unsafe {
                let name = msg!(() -> Id)(e, selp("name"));
                let reason = msg!(() -> Id)(e, selp("reason"));
                eprintln!("[EXC] {} -- {}", ns_str(name), ns_str(reason));
            }
        }
        unsafe {
            NSSetUncaughtExceptionHandler(on_exc);
        }
        const CANDIDATES: &[&str] = &[
            "perfStats",
            "perf_stats",
            "performanceStats",
            "performanceStatistics",
            "latestPerfStats",
            "hwPerformanceStats",
            "executionStats",
            "executionStatistics",
            "statsMask",
            "perfStatistics",
            "profilingResults",
            "profilingStats",
            "procedureStats",
            "taskStats",
            "driverStats",
            "aneStats",
            "durations",
            "hwDurations",
            "modelAttributes",
            "attributes",
            "stats",
        ];
        unsafe {
            // Stats need the mask on the model property itself, not
            // just the load options.
            let _ = msg!((u64) -> ())(self.model, selp("setPerfStatsMask:"), 0x7fu64);
            // The stats lane: `initWithInputs:...:perfStats:` takes a
            // `_ANEPerformanceStats` wrapping an IOSurface — verified
            // end-to-end (object, request, XPC hand-off all build).
            // But eval throws unless the program was compiled with
            // stats instrumentation (`ProgramCreate stats buffer
            // size:0` in the ANEServices log) — gated so the probe
            // still works on ordinary binaries.
            // Session-hint reporting lane: start a session around the
            // eval and read the report — independent of program-level
            // stats instrumentation.
            // Resolve the exported hint constants — names in the export
            // table, values in the objects they point at.
            for k in [
                "kANEFHintSessionStart",
                "kANEFHintSessionStop",
                "kANEFHintSessionInfo",
                "kANEFHintSessionAbort",
                "kANEFHintReportSessionStatusKey",
                "kANEFHintReportTotalPagesKey",
                "kANEFHintReportResidentPagesKey",
                "kANEFHintEnergyEfficientWorkloadKey",
                "kANEFHintSessionInfo",
                "kANEFModelLoadPerformanceStats",
            ] {
                match self.ksym(k) {
                    Some((_, v)) => eprintln!("[ksym] {k} = {v:?}"),
                    None => eprintln!("[ksym] {k} MISSING"),
                }
            }
            let hint = |name: &str, report_out: &mut Vec<(String, String, String)>| {
                let mut err: Id = std::ptr::null_mut();
                let obj = self
                    .ksym(name)
                    .map(|(o, _)| o)
                    .unwrap_or_else(|| self.objc.ns_string(name));
                // Request all report kinds in options; hand the daemon a
                // mutable dict to fill.
                let want = [
                    "ANEClientSessionStatus",
                    "ANEClientTotalPages",
                    "ANEClientResidentPages",
                ];
                let keys: Vec<Id> = want.iter().map(|k| self.objc.ns_string(k)).collect();
                let vals: Vec<Id> = want.iter().map(|_| self.objc.ns_int(1)).collect();
                let opts = msg!((*const Id, *const Id, usize) -> Id)(
                    self.objc.ns_dict,
                    selp("dictionaryWithObjects:forKeys:count:"),
                    vals.as_ptr(),
                    keys.as_ptr(),
                    keys.len(),
                );
                let mdict_cls = objc_getClass(cstr("NSMutableDictionary").as_ptr());
                let report = msg!(() -> Id)(mdict_cls, selp("dictionary"));
                // B56@0:8@16@24@32@40^@48 — model, hint, options,
                // report (plain object arg), error (NSError **).
                let ok = msg!((Id, Id, Id, Id, *mut Id) -> bool)(
                    self.client,
                    selp("sessionHintWithModel:hint:options:report:error:"),
                    self.model,
                    obj,
                    opts,
                    report,
                    &mut err,
                );
                eprintln!(
                    "[hint] {name} -> ok={ok} err={} report={report:?}",
                    err_desc(err)
                );
                if !report.is_null() {
                    for k in self.objc.dict_keys(report) {
                        let v = msg!((Id) -> Id)(
                            report,
                            selp("objectForKey:"),
                            self.objc.ns_string(&k),
                        );
                        let d = if v.is_null() {
                            String::new()
                        } else {
                            ns_str(msg!(() -> Id)(v, selp("description")))
                        };
                        let mut s = d;
                        if s.len() > 600 {
                            s.truncate(600);
                            s.push('…');
                        }
                        report_out.push(("sessionReport".into(), k, s));
                    }
                }
            };
            let mut hint_hits = Vec::new();
            hint("kANEFHintSessionStart", &mut hint_hits);
            let req = if std::env::var_os("ESP_STATS_REQ").is_some() {
                self.make_request_stats(0)?
            } else {
                self.make_request(0)?
            };
            self.eval_request(req)?;
            hint("kANEFHintSessionStop", &mut hint_hits);
            hint("kANEFHintSessionInfo", &mut hint_hits);

            let mut hits = hint_hits;
            let stats_arr = msg!(() -> Id)(req, selp("perfStatsArray"));
            if !stats_arr.is_null() {
                let d = msg!(() -> Id)(stats_arr, selp("description"));
                hits.push(("request".into(), "perfStatsArray".into(), ns_str(d)));
            }
            let stats = msg!(() -> Id)(req, selp("perfStats"));
            if !stats.is_null() {
                let d = msg!(() -> Id)(stats, selp("description"));
                hits.push(("request".into(), "perfStats".into(), ns_str(d)));
                // `_ANEPerformanceStatsIOSurface` unwraps to the decoded
                // `_ANEPerformanceStats` via its `stats` property.
                let inner = msg!(() -> Id)(stats, selp("stats"));
                let target = if inner.is_null() { stats } else { inner };
                for &k in &[
                    "hwExecutionTime",
                    "perfCounterData",
                    "pStatsRawData",
                    "performanceCounters",
                ] {
                    let v = msg!(() -> Id)(target, selp(k));
                    if !v.is_null() {
                        let d = msg!(() -> Id)(v, selp("description"));
                        let mut s = ns_str(d);
                        if s.len() > 2000 {
                            s.truncate(2000);
                            s.push('…');
                        }
                        hits.push(("perfStats".into(), k.into(), s));
                    }
                }
                let hw = msg!(() -> f64)(target, selp("hwExecutionTime"));
                hits.push((
                    "perfStats".into(),
                    "hwExecutionTime".into(),
                    format!("{hw}"),
                ));
            }
            let probe = |hits: &mut Vec<(String, String, String)>, target: &str, obj: Id| {
                for &k in CANDIDATES {
                    // valueForKey: throws on unknown keys — only call the
                    // getter when the object declares it.
                    let responds = msg!((Id) -> bool)(obj, selp("respondsToSelector:"), selp(k));
                    if !responds {
                        continue;
                    }
                    let v = msg!(() -> Id)(obj, selp(k));
                    if !v.is_null() {
                        let d = msg!(() -> Id)(v, selp("description"));
                        let mut s = ns_str(d);
                        if s.len() > 400 {
                            s.truncate(400);
                            s.push('…');
                        }
                        hits.push((target.to_string(), k.to_string(), s));
                    }
                }
            };
            probe(&mut hits, "model", self.model);
            probe(&mut hits, "client", self.client);
            probe(&mut hits, "request", req);
            // Dump modelAttributes' top-level keys — the stats may land
            // inside the attrs dict rather than on a property.
            let attrs = msg!((Id) -> Id)(
                self.model,
                selp("valueForKey:"),
                self.objc.ns_string("modelAttributes"),
            );
            if !attrs.is_null() {
                for k in self.objc.dict_keys(attrs) {
                    hits.push(("modelAttributes".into(), k, String::new()));
                }
            }
            Ok(hits)
        }
    }

    fn eval_inner(&self, proc: u64) -> Result<(), EspError> {
        unsafe {
            let in_objs: Vec<Id> = self.inputs.iter().map(|s| s.wrap).collect();
            let out_objs: Vec<Id> = self.outputs.iter().map(|s| s.wrap).collect();
            let in_idx: Vec<Id> = (0..self.inputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let out_idx: Vec<Id> = (0..self.outputs.len() as u64)
                .map(|i| self.objc.ns_int(i))
                .collect();
            let proc_idx = self.objc.ns_int(proc);
            let ins = self.objc.ns_arr(&in_objs);
            let ins_i = self.objc.ns_arr(&in_idx);
            let outs = self.objc.ns_arr(&out_objs);
            let outs_i = self.objc.ns_arr(&out_idx);
            let req = msg!((Id, Id, Id, Id, Id) -> Id)(
                self.objc.ane_request,
                selp("requestWithInputs:inputIndices:outputs:outputIndices:procedureIndex:"),
                ins,
                ins_i,
                outs,
                outs_i,
                proc_idx,
            );
            if req.is_null() {
                return Err(EspError::Msg("_ANERequest init failed".into()));
            }
            let valid = msg!(() -> bool)(req, selp("validate"));
            if !valid {
                return Err(EspError::Msg("_ANERequest validate failed".into()));
            }
            let opts = self.objc.empty_dict();
            let mut err: Id = std::ptr::null_mut();
            let ok = msg!((Id, Id, Id, *mut Id) -> bool)(
                self.client,
                selp("evaluateRealTimeWithModel:options:request:error:"),
                self.model,
                opts,
                req,
                &mut err,
            );
            if ok {
                Ok(())
            } else {
                Err(EspError::Msg(format!("evaluate failed: {}", err_desc(err))))
            }
        }
    }
}

/// NSString → String via `UTF8String` ("" for null/non-strings).
fn ns_str(o: Id) -> String {
    if o.is_null() {
        return String::new();
    }
    unsafe {
        let p = msg!(() -> *const c_char)(o, selp("UTF8String"));
        if p.is_null() {
            String::new()
        } else {
            std::ffi::CStr::from_ptr(p).to_string_lossy().into_owned()
        }
    }
}

fn u64v(o: Id, name: &str) -> u64 {
    unsafe {
        let ns = objc_getClass(cstr("NSString").as_ptr());
        let k = msg!((Id) -> Id)(ns, selp("stringWithUTF8String:"), cstr(name).as_ptr() as Id);
        let v = msg!((Id) -> Id)(o, selp("valueForKey:"), k);
        if v.is_null() {
            0
        } else {
            msg!(() -> u64)(v, selp("unsignedLongLongValue"))
        }
    }
}

fn err_desc(err: Id) -> String {
    if err.is_null() {
        return "unknown".into();
    }
    unsafe {
        let d = msg!(() -> Id)(err, selp("localizedDescription"));
        if d.is_null() {
            return "NSError".into();
        }
        let p = msg!(() -> *const c_char)(d, selp("UTF8String"));
        if p.is_null() {
            "NSError".into()
        } else {
            std::ffi::CStr::from_ptr(p).to_string_lossy().into_owned()
        }
    }
}

impl Drop for EspressoProgram {
    fn drop(&mut self) {
        unsafe {
            let opts = self.objc.empty_dict();
            let mut err: Id = std::ptr::null_mut();
            let f = msg!((Id, Id, u64, *mut Id) -> bool);
            let _ = f(
                self.client,
                selp("unloadModel:options:qos:error:"),
                self.model,
                opts,
                0,
                &mut err,
            );
        }
        for s in self.inputs.iter().chain(self.outputs.iter()) {
            if s.owned {
                release(s.wrap);
                unsafe { (self.io.cf_release)(s.surf) };
            }
        }
        release(self.model);
        release(self.client);
    }
}

unsafe impl Send for EspressoProgram {}
unsafe impl Sync for EspressoProgram {}

#[cfg(test)]
mod run1_tests {
    use super::{AneLoadError, AneLoadKind, ArtifactForm};

    /// The exact description an `_ANEClient loadModel:error:` refusal produces,
    /// captured from hardware (PROBE-2 / `examples/raw_err.rs`). Verbatim, not
    /// paraphrased — the tokenisation depends on the selector text.
    const REAL_170004: &str = "loadModel failed: createProgramInstanceForModel:modelToken:modelFilePath:qos:isPreCompiled:enablePowerSaving:skipPreparePhase:statsMask:memoryPoolID:enableLateLatch:modelIdentityStr:owningPid:cacheUrlIdentifier:aotCacheUrlIdentifier:optOutOfModelMemoryUnwiring:error:: Program load failure (0x170004)";

    /// The measured code table (docs/evidence/0010-deploy-gate-codes.md):
    /// code → (kind, form). This is the RUN-1 acceptance table.
    #[test]
    fn every_measured_code_decodes_to_a_named_variant() {
        let table = [
            (0x170004u32, AneLoadKind::BareMachoRejected, ArtifactForm::BareMacho),
            (0x130004, AneLoadKind::EspressoBundleRejected, ArtifactForm::EspressoBundle),
            (0x120004, AneLoadKind::E5BundleRejected, ArtifactForm::E5Bundle),
        ];
        for (code, kind, form) in table {
            let e = AneLoadError::decode(format!("Program load failure (0x{code:06X})"));
            assert_eq!(e.code, Some(code), "code for 0x{code:06X}");
            assert_eq!(e.kind, kind, "kind for 0x{code:06X}");
            assert_eq!(e.form, Some(form), "form for 0x{code:06X}");
            assert!(
                e.is_known_deploy_gate(),
                "0x{code:06X} is a measured deploy-gate code"
            );
            assert!(
                e.suggested_cause().is_some(),
                "0x{code:06X} must suggest a cause"
            );
        }
    }

    #[test]
    fn real_captured_description_decodes() {
        let e = AneLoadError::decode(REAL_170004);
        assert_eq!(e.code, Some(0x170004));
        assert_eq!(e.kind, AneLoadKind::BareMachoRejected);
        assert_eq!(e.form, Some(ArtifactForm::BareMacho));
        // The raw text is preserved so a new code stays debuggable.
        assert!(
            e.raw.contains("createProgramInstanceForModel"),
            "raw description must be retained verbatim"
        );
    }

    /// A code outside the measured table must NOT be silently mapped onto a
    /// known one. This is the guard against over-claiming a taxonomy.
    #[test]
    fn unrecognised_code_is_not_guessed() {
        let e = AneLoadError::decode("Program load failure (0x1F0004)");
        assert_eq!(e.code, Some(0x001F0004));
        assert_eq!(e.kind, AneLoadKind::Unrecognised);
        assert_eq!(e.form, None, "an unknown code has no known form");
        assert!(
            e.suggested_cause().is_none(),
            "must not invent a cause for an unmeasured code"
        );
        assert!(!e.is_known_deploy_gate());
        // Still debuggable.
        assert!(e.to_string().contains("unrecognised code"));
        assert!(e.to_string().contains("0x1F0004"));
    }

    #[test]
    fn missing_code_is_reported_as_such() {
        let e = AneLoadError::decode("loadModel failed: connection invalid");
        assert_eq!(e.code, None);
        assert_eq!(e.kind, AneLoadKind::NoCode);
        assert_eq!(e.form, None);
        assert!(e.suggested_cause().is_none());
        assert!(e.to_string().contains("no code"));
    }

    /// The code arrives as a signed `NSInteger`, so a `-` prefix must not
    /// defeat the decode. `dp3.rs` originally sliced 8 chars and produced
    /// "-0x17000" for this case.
    #[test]
    fn negative_prefixed_code_still_decodes() {
        let e = AneLoadError::decode("Program load failure (-0x170004)");
        assert_eq!(
            e.code,
            Some(0x170004),
            "a leading '-' must not corrupt the code"
        );
        assert_eq!(e.kind, AneLoadKind::BareMachoRejected);
    }

    /// A truncated or malformed token yields no code rather than a wrong one.
    #[test]
    fn malformed_token_yields_no_code() {
        for bad in ["0x", "0xZZZ", "failure (0x)"] {
            let e = AneLoadError::decode(format!("Program load failure ({bad})"));
            assert_eq!(e.code, None, "{bad:?} must not parse as a code");
            assert_eq!(e.kind, AneLoadKind::NoCode);
        }
    }

    /// A terminal parenthesised code beats an earlier hex token.
    ///
    /// FORK(ane-stack): this test originally asserted the opposite — that the
    /// *first* `0x` token wins ("model 0xABCDEF failed with (0x170004)" →
    /// `0xABCDEF`). That assumption predates macOS 27.x, whose description is
    /// `... Program load failed - bad program image (model may be corrupt or
    /// incompatible) (underlying=0x13)`: the only hex token is the nested code,
    /// and there is no earlier token to confuse it with. But a 26.x-style
    /// description rewritten with an incidental earlier token must still
    /// resolve to its parenthesised code, which the first-token rule gets
    /// wrong. Corrected to assert the terminal-code rule, which subsumes the
    /// original intent (selector text must not win) and fixes the 27.x case.
    /// Upstream: 20f097f.
    #[test]
    fn parenthesised_trailing_code_beats_earlier_hex_token() {
        let e = AneLoadError::decode("model 0xABCDEF failed with (0x170004)");
        assert_eq!(
            e.code,
            Some(0x170004),
            "the parenthesised code must beat incidental selector hex"
        );
    }

    #[test]
    fn presented_form_is_inferred_from_the_path() {
        use std::path::Path;
        assert_eq!(
            ArtifactForm::from_path(Path::new("/tmp/sig.macho")),
            Some(ArtifactForm::BareMacho)
        );
        assert_eq!(
            ArtifactForm::from_path(Path::new(
                "/System/Library/x/cnn_frame_enhancer_192p.H16.espresso.hwx"
            )),
            Some(ArtifactForm::EspressoBundle)
        );
        assert_eq!(
            ArtifactForm::from_path(Path::new("/tmp/c/H17C.bundle/H17C.e5")),
            Some(ArtifactForm::E5Bundle)
        );
        assert_eq!(ArtifactForm::from_path(Path::new("/tmp/model.mil")), None);
    }

    /// Display must always name the code when there is one, and always carry
    /// the raw text — an operator's only handle on a novel failure.
    #[test]
    fn display_never_hides_the_code_or_raw_text() {
        let e = AneLoadError::decode(REAL_170004);
        let s = e.to_string();
        assert!(s.contains("0x170004"), "Display must name the code: {s}");
        assert!(
            s.contains("createProgramInstanceForModel"),
            "Display must carry the raw description: {s}"
        );
    }
}

#[cfg(test)]
mod run1_os_shapes {
    use super::{AneLoadError, AneLoadKind};

    /// macOS 26.x: the code is a parenthesised trailing token.
    const MACOS_26_SHAPE: &str = "loadModel failed: createProgramInstanceForModel:modelToken:modelFilePath:qos:isPreCompiled:enablePowerSaving:skipPreparePhase:statsMask:memoryPoolID:enableLateLatch:modelIdentityStr:owningPid:cacheUrlIdentifier:aotCacheUrlIdentifier:optOutOfModelMemoryUnwiring:error:: Program load failure (0x170004)";

    /// macOS 27.x: a human-readable cause plus a NESTED underlying code.
    /// Captured verbatim from a real 27.0 refusal (`raw_err_dp`).
    const MACOS_27_SHAPE: &str = "loadModel failed: createProgramInstanceForModel:modelToken:modelFilePath:qos:isPreCompiled:enablePowerSaving:skipPreparePhase:statsMask:memoryPoolID:enableLateLatch:modelIdentityStr:owningPid:cacheUrlIdentifier:aotCacheUrlIdentifier:optOutOfModelMemoryUnwiring:intermediateBufferSizeHint:error:: Program load failed — bad program image (model may be corrupt or incompatible) (underlying=0x13)";

    /// The 26.x shape must still parse — this is the case that regressed into
    /// `Some(19)` under a naive first-token rule once 27.x existed.
    #[test]
    fn macos26_shape_still_parses() {
        let e = AneLoadError::decode(MACOS_26_SHAPE);
        assert_eq!(e.code, Some(0x170004));
        assert_eq!(e.kind, AneLoadKind::BareMachoRejected);
    }

    /// The 27.x shape must parse its NESTED code, not `0x13` read as 19.
    #[test]
    fn macos27_shape_parses_underlying() {
        let e = AneLoadError::decode(MACOS_27_SHAPE);
        assert_eq!(e.code, Some(0x13), "underlying=0x13 must be the code");
    }

    /// `underlying=` wins over an earlier `(0x…)` in the same description. This
    /// is the macOS 27.x ordering: a parenthesised selector token may precede
    /// the nested `underlying=` code.
    #[test]
    fn underlying_wins_over_earlier_paren() {
        let s = "blah (0xdeadbeef) underlying=0x13 more text";
        let e = AneLoadError::decode(s);
        assert_eq!(e.code, Some(0x13));
    }

    /// The parenthesised form still works when there is no `underlying=`.
    #[test]
    fn paren_form_wins_over_first_token() {
        let s = "selector text 0xBAD then ... Program load failure (0x170004)";
        let e = AneLoadError::decode(s);
        assert_eq!(e.code, Some(0x170004));
    }

    #[test]
    fn still_no_code_when_none_present() {
        let e = AneLoadError::decode("connection invalid");
        assert_eq!(e.code, None);
        assert_eq!(e.kind, AneLoadKind::NoCode);
    }

    #[test]
    fn signed_paren_still_parses() {
        let e = AneLoadError::decode("Program load failure (-0x170004)");
        assert_eq!(e.code, Some(0x170004));
    }
}
