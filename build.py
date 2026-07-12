#!/usr/bin/env python3
"""
m-engine V1 Workspace Builder
==============================
Reconstructs the complete m-engine Cargo workspace with all 8 modules,
writes every source file, and bundles into m-engine.zip.
"""

import os
import zipfile

# =============================================================================
# FILE CONTENTS
# =============================================================================

FILES = {
    # -------------------------------------------------------------------------
    # Workspace Root
    # -------------------------------------------------------------------------
    "Cargo.toml": '''[workspace]
members = [
    "crates/platform",
    "crates/memory",
    "crates/dom",
    "crates/html",
    "crates/javascript",
    "crates/css",
    "crates/layout",
    "crates/renderer",
]
resolver = "2"

[workspace.package]
version = "0.1.0"
edition = "2021"
authors = ["m-engine Team"]
rust-version = "1.78"
''',

    # -------------------------------------------------------------------------
    # Module 1: Platform
    # -------------------------------------------------------------------------
    "crates/platform/Cargo.toml": '''[package]
name = "platform"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
libc = "0.2"
''',

    "crates/platform/src/lib.rs": '''//! # Platform Initialization
//!
//! Hardware capability detection, capability profile selection, and engine
//! configuration derivation. This is the first subsystem initialized at startup.
//! All downstream subsystems (memory, DOM, render) depend on the profile
//! selected here.

pub mod detection;
pub mod profile;

pub use detection::{HardwareInfo, Platform};
pub use profile::{
    CacheLimits, CapabilityProfile, EngineConfig, PrefetchConfig, TargetFramerate,
};
''',

    "crates/platform/src/profile.rs": '''//! Capability Profiles and Engine Configuration
//!
//! Defines the four hardware-adaptive profiles (Embedded, Low, Standard, High)
//! and derives deterministic engine behavior from each.

use std::num::NonZeroUsize;

/// The four hardware capability profiles defined by the specification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CapabilityProfile {
    /// < 1 GB RAM. Aggressive limits, immediate flush.
    Embedded,
    /// 1 GB – 2 GB RAM. Minimal caches, inline compression.
    Low,
    /// 2 GB – 4 GB RAM. Standard buffers, full prefetch if cores allow.
    Standard,
    /// > 4 GB RAM. Aggressive pre-rendering and cache.
    High,
}

impl CapabilityProfile {
    /// Select the appropriate profile based on detected hardware.
    ///
    /// # Specification Mapping
    /// - Embedded: `< 1 GB`
    /// - Low: `1 GB – 2 GB`
    /// - Standard: `2 GB – 4 GB`
    /// - High: `> 4 GB`
    pub fn from_hardware(hw: &HardwareInfo) -> Self {
        match hw.total_ram_bytes {
            0..=1_073_741_824 => Self::Embedded,
            1_073_741_825..=2_147_483_648 => Self::Low,
            2_147_483_649..=4_294_967_296 => Self::Standard,
            _ => Self::High,
        }
    }

    /// Derive the full engine configuration for this profile.
    pub fn to_config(self, hw: &HardwareInfo) -> EngineConfig {
        EngineConfig::from_profile(self, hw)
    }
}

/// Target display framerate behavior.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TargetFramerate {
    /// Adaptive 30–60 FPS based on workload.
    Adaptive,
    /// Locked to 30 FPS to reduce power/thermal load.
    Stable30,
    /// Locked to 60 FPS.
    Fixed60,
    /// Uncapped; VSync only.
    Uncapped,
}

/// Prefetch behavior configuration.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrefetchConfig {
    /// No speculative resource loading.
    Disabled,
    /// Selective prefetch based on viewport heuristics.
    Selective,
    /// Full prefetch pipeline active.
    Full,
}

/// Memory cache limits per profile.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CacheLimits {
    /// Maximum decoded image cache in bytes.
    pub image_cache_bytes: usize,
    /// Maximum CSS computed style cache entries.
    pub style_cache_entries: usize,
    /// Maximum network response cache in bytes.
    pub network_cache_bytes: usize,
    /// Maximum JavaScript bytecode cache in bytes.
    pub js_bytecode_cache_bytes: usize,
}

/// Complete engine configuration derived from a capability profile.
///
/// This struct is immutable after creation and is shared read-only across
/// all engine subsystems. It is typically stored in a `Platform` singleton.
#[derive(Debug, Clone)]
pub struct EngineConfig {
    pub profile: CapabilityProfile,
    pub target_framerate: TargetFramerate,
    pub prefetch: PrefetchConfig,
    /// JavaScript JIT compilation enabled.
    pub jit_enabled: bool,
    /// CSS parallel matching enabled (depends on core count).
    pub parallel_matching: bool,
    pub cache_limits: CacheLimits,
    /// Memory pressure threshold in bytes. When exceeded, aggressive eviction
    /// and flush are triggered.
    pub memory_pressure_threshold: usize,
    /// Minimum number of CPU cores required to enable parallel matching.
    pub parallel_matching_min_cores: usize,
}

/// Hardware snapshot detected at startup.
#[derive(Debug, Clone)]
pub struct HardwareInfo {
    /// Total physical RAM in bytes.
    pub total_ram_bytes: u64,
    /// Number of logical CPU cores.
    pub cpu_cores: usize,
    /// CPU cache line size in bytes (detected or default 64).
    pub cache_line_size: usize,
    /// Page size in bytes.
    pub page_size: usize,
}

impl HardwareInfo {
    /// Create a HardwareInfo with explicit values (useful for testing).
    pub const fn new(total_ram_bytes: u64, cpu_cores: usize) -> Self {
        Self {
            total_ram_bytes,
            cpu_cores,
            cache_line_size: 64,
            page_size: 4096,
        }
    }
}

impl EngineConfig {
    /// Build configuration strictly according to the architectural specification.
    pub fn from_profile(profile: CapabilityProfile, hw: &HardwareInfo) -> Self {
        match profile {
            CapabilityProfile::Embedded => Self {
                profile,
                target_framerate: TargetFramerate::Adaptive,
                prefetch: PrefetchConfig::Disabled,
                jit_enabled: false,
                parallel_matching: false,
                cache_limits: CacheLimits {
                    image_cache_bytes: 4 * 1024 * 1024,
                    style_cache_entries: 256,
                    network_cache_bytes: 2 * 1024 * 1024,
                    js_bytecode_cache_bytes: 1 * 1024 * 1024,
                },
                memory_pressure_threshold: 64 * 1024 * 1024,
                parallel_matching_min_cores: usize::MAX,
            },
            CapabilityProfile::Low => Self {
                profile,
                target_framerate: TargetFramerate::Stable30,
                prefetch: PrefetchConfig::Selective,
                jit_enabled: false,
                parallel_matching: false,
                cache_limits: CacheLimits {
                    image_cache_bytes: 8 * 1024 * 1024,
                    style_cache_entries: 1024,
                    network_cache_bytes: 4 * 1024 * 1024,
                    js_bytecode_cache_bytes: 2 * 1024 * 1024,
                },
                memory_pressure_threshold: 128 * 1024 * 1024,
                parallel_matching_min_cores: usize::MAX,
            },
            CapabilityProfile::Standard => Self {
                profile,
                target_framerate: TargetFramerate::Fixed60,
                prefetch: PrefetchConfig::Full,
                jit_enabled: true,
                parallel_matching: hw.cpu_cores >= 4,
                cache_limits: CacheLimits {
                    image_cache_bytes: 32 * 1024 * 1024,
                    style_cache_entries: 4096,
                    network_cache_bytes: 16 * 1024 * 1024,
                    js_bytecode_cache_bytes: 8 * 1024 * 1024,
                },
                memory_pressure_threshold: 256 * 1024 * 1024,
                parallel_matching_min_cores: 4,
            },
            CapabilityProfile::High => Self {
                profile,
                target_framerate: TargetFramerate::Uncapped,
                prefetch: PrefetchConfig::Full,
                jit_enabled: true,
                parallel_matching: true,
                cache_limits: CacheLimits {
                    image_cache_bytes: 128 * 1024 * 1024,
                    style_cache_entries: 16384,
                    network_cache_bytes: 64 * 1024 * 1024,
                    js_bytecode_cache_bytes: 32 * 1024 * 1024,
                },
                memory_pressure_threshold: 512 * 1024 * 1024,
                parallel_matching_min_cores: 2,
            },
        }
    }

    /// Returns true if the engine should run CSS matching in parallel.
    pub fn parallel_matching_enabled(&self, hw: &HardwareInfo) -> bool {
        self.parallel_matching && hw.cpu_cores >= self.parallel_matching_min_cores
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profile_selection_ram_boundaries() {
        let embedded = HardwareInfo::new(512 * 1024 * 1024, 2);
        let low = HardwareInfo::new(1536 * 1024 * 1024, 4);
        let standard = HardwareInfo::new(3 * 1024 * 1024 * 1024, 4);
        let high = HardwareInfo::new(8 * 1024 * 1024 * 1024, 8);

        assert_eq!(CapabilityProfile::from_hardware(&embedded), CapabilityProfile::Embedded);
        assert_eq!(CapabilityProfile::from_hardware(&low), CapabilityProfile::Low);
        assert_eq!(CapabilityProfile::from_hardware(&standard), CapabilityProfile::Standard);
        assert_eq!(CapabilityProfile::from_hardware(&high), CapabilityProfile::High);
    }

    #[test]
    fn standard_parallel_matching_gate() {
        let hw_4core = HardwareInfo::new(3 * 1024 * 1024 * 1024, 4);
        let cfg = EngineConfig::from_profile(CapabilityProfile::Standard, &hw_4core);
        assert!(cfg.parallel_matching_enabled(&hw_4core));

        let hw_2core = HardwareInfo::new(3 * 1024 * 1024 * 1024, 2);
        assert!(!cfg.parallel_matching_enabled(&hw_2core));
    }

    #[test]
    fn embedded_never_parallel() {
        let hw = HardwareInfo::new(512 * 1024 * 1024, 64);
        let cfg = EngineConfig::from_profile(CapabilityProfile::Embedded, &hw);
        assert!(!cfg.parallel_matching_enabled(&hw));
        assert!(!cfg.jit_enabled);
    }
}
''',

    "crates/platform/src/detection.rs": '''//! Hardware Detection
//!
//! Detects total RAM, CPU core count, cache line size, and page size at
//! engine startup. All detection is performed once and cached in the `Platform`
//! singleton.

use super::profile::{CapabilityProfile, EngineConfig, HardwareInfo};
use std::sync::OnceLock;

/// Platform singleton initialized at engine startup.
///
/// This is the root of all capability-dependent configuration. Subsystems
/// receive an `&EngineConfig` or `&HardwareInfo` rather than querying the
/// platform directly, to keep dependencies explicit and testable.
#[derive(Debug, Clone)]
pub struct Platform {
    pub hardware: HardwareInfo,
    pub profile: CapabilityProfile,
    pub config: EngineConfig,
}

/// Errors that can occur during platform initialization.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PlatformError {
    /// Failed to detect a specific hardware property.
    DetectionFailed(&'static str),
    /// The current platform is not supported.
    UnsupportedPlatform,
}

impl Platform {
    /// Initialize the platform layer.
    ///
    /// This performs exactly one system query for each hardware property and
    /// derives the capability profile. It must be called before any other
    /// engine subsystem is initialized.
    pub fn initialize() -> Result<Self, PlatformError> {
        let hardware = detect_hardware()?;
        let profile = CapabilityProfile::from_hardware(&hardware);
        let config = EngineConfig::from_profile(profile, &hardware);

        Ok(Self {
            hardware,
            profile,
            config,
        })
    }

    /// Initialize with explicit hardware info (useful for testing and
    /// deterministic embedded targets).
    pub fn from_hardware(hardware: HardwareInfo) -> Self {
        let profile = CapabilityProfile::from_hardware(&hardware);
        let config = EngineConfig::from_profile(profile, &hardware);
        Self {
            hardware,
            profile,
            config,
        }
    }
}

/// Detect hardware properties from the operating system.
fn detect_hardware() -> Result<HardwareInfo, PlatformError> {
    let total_ram_bytes = detect_total_ram()
        .ok_or(PlatformError::DetectionFailed("total_ram"))?;
    let cpu_cores = detect_cpu_cores()
        .ok_or(PlatformError::DetectionFailed("cpu_cores"))?;
    let cache_line_size = detect_cache_line_size();
    let page_size = detect_page_size();

    Ok(HardwareInfo {
        total_ram_bytes,
        cpu_cores,
        cache_line_size,
        page_size,
    })
}

// ---------------------------------------------------------------------------
// OS-Specific Implementations
// ---------------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn detect_total_ram() -> Option<u64> {
    // SAFETY: sysinfo is a standard Linux syscall with well-defined behavior.
    unsafe {
        let mut info: libc::sysinfo = std::mem::zeroed();
        if libc::sysinfo(&mut info) == 0 {
            Some(info.totalram as u64 * info.mem_unit as u64)
        } else {
            None
        }
    }
}

#[cfg(target_os = "macos")]
fn detect_total_ram() -> Option<u64> {
    use std::mem;
    // SAFETY: sysctl with CTL_HW and HW_MEMSIZE is the standard macOS API.
    unsafe {
        let mut mib = [libc::CTL_HW, libc::HW_MEMSIZE];
        let mut memsize: u64 = 0;
        let mut len = mem::size_of::<u64>();
        let ret = libc::sysctl(
            mib.as_mut_ptr(),
            2,
            &mut memsize as *mut _ as *mut libc::c_void,
            &mut len,
            std::ptr::null_mut(),
            0,
        );
        if ret == 0 { Some(memsize) } else { None }
    }
}

#[cfg(target_os = "windows")]
fn detect_total_ram() -> Option<u64> {
    // SAFETY: GlobalMemoryStatusEx is the standard Windows API.
    unsafe {
        let mut status: MEMORYSTATUSEX = std::mem::zeroed();
        status.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
        if GlobalMemoryStatusEx(&mut status) != 0 {
            Some(status.ullTotalPhys)
        } else {
            None
        }
    }
}

#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
fn detect_total_ram() -> Option<u64> {
    None
}

fn detect_cpu_cores() -> Option<usize> {
    // std::thread::available_parallelism is stable and reliable across platforms.
    std::thread::available_parallelism()
        .ok()
        .and_then(NonZeroUsize::get)
}

fn detect_cache_line_size() -> usize {
    // Most modern x86_64 and ARM64 processors use 64-byte cache lines.
    64
}

fn detect_page_size() -> usize {
    static PAGE_SIZE: OnceLock<usize> = OnceLock::new();
    *PAGE_SIZE.get_or_init(|| {
        #[cfg(unix)]
        unsafe {
            libc::sysconf(libc::_SC_PAGESIZE) as usize
        }
        #[cfg(target_os = "windows")]
        unsafe {
            let mut info: SYSTEM_INFO = std::mem::zeroed();
            GetSystemInfo(&mut info);
            info.dwPageSize as usize
        }
        #[cfg(not(any(unix, target_os = "windows")))]
        {
            4096
        }
    })
}

// ---------------------------------------------------------------------------
// Windows FFI (minimal, no external crate dependency)
// ---------------------------------------------------------------------------

#[cfg(target_os = "windows")]
#[repr(C)]
struct MEMORYSTATUSEX {
    dwLength: u32,
    dwMemoryLoad: u32,
    ullTotalPhys: u64,
    ullAvailPhys: u64,
    ullTotalPageFile: u64,
    ullAvailPageFile: u64,
    ullTotalVirtual: u64,
    ullAvailVirtual: u64,
    ullAvailExtendedVirtual: u64,
}

#[cfg(target_os = "windows")]
#[repr(C)]
struct SYSTEM_INFO {
    dwPageSize: u32,
    lpMinimumApplicationAddress: *mut libc::c_void,
    lpMaximumApplicationAddress: *mut libc::c_void,
    dwActiveProcessorMask: *mut libc::c_void,
    dwNumberOfProcessors: u32,
    dwProcessorType: u32,
    dwAllocationGranularity: u32,
    wProcessorLevel: u16,
    wProcessorRevision: u16,
}

#[cfg(target_os = "windows")]
extern "system" {
    fn GlobalMemoryStatusEx(lpBuffer: *mut MEMORYSTATUSEX) -> i32;
    fn GetSystemInfo(lpSystemInfo: *mut SYSTEM_INFO);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn platform_init_success() {
        if let Ok(platform) = Platform::initialize() {
            assert!(platform.hardware.total_ram_bytes > 0);
            assert!(platform.hardware.cpu_cores > 0);
            assert!(platform.hardware.page_size >= 4096);
            assert!(matches!(
                platform.profile,
                CapabilityProfile::Embedded
                    | CapabilityProfile::Low
                    | CapabilityProfile::Standard
                    | CapabilityProfile::High
            ));
        }
    }

    #[test]
    fn from_hardware_deterministic() {
        let hw = HardwareInfo::new(2 * 1024 * 1024 * 1024, 4);
        let platform = Platform::from_hardware(hw);
        assert_eq!(platform.profile, CapabilityProfile::Standard);
        assert_eq!(platform.config.target_framerate, TargetFramerate::Fixed60);
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 2: Memory
    # -------------------------------------------------------------------------
    "crates/memory/Cargo.toml": '''[package]
name = "memory"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
platform = { path = "../platform" }
libc = "0.2"
''',

    "crates/memory/src/lib.rs": '''//! # Memory Subsystem
//!
//! The Tiered Allocator System bypasses the OS universal allocator for all
//! critical engine data. It provides:
//!
//! 1. **SlabAllocator** — O(1) fixed-size allocation via bitmaps.
//! 2. **ArenaAllocator** — Bump-pointer linear allocation with bulk reset.
//! 3. **DirectAllocator** — OS `mmap`/`VirtualAlloc` for massive objects.
//! 4. **TieredAllocator** — The unified registry where each subsystem selects
//!    its dedicated allocator.
//!
//! ## Safety & Invariants
//!
//! - Slab and Arena allocators are **NOT thread-safe**. They must be owned by
//!   a single thread or wrapped in external synchronization.
//! - No system `malloc`/`free` is called on the allocation hot path.
//! - All backing memory comes from `mmap` (or `VirtualAlloc` on Windows) and
//!   is returned directly to the OS on drop.

pub mod arena;
pub mod bench;
pub mod direct;
pub mod slab;
pub mod tiered;
pub mod traits;

pub use arena::ArenaAllocator;
pub use direct::DirectAllocator;
pub use slab::SlabAllocator;
pub use tiered::TieredAllocator;
pub use traits::{ArenaAlloc, RawAllocator, SlabAlloc};
''',

    "crates/memory/src/traits.rs": '''//! Allocator traits defining the minimal interface required by engine
//! subsystems. These traits intentionally do NOT mirror `GlobalAlloc`; they
//! are specialized for our deterministic, zero-allocation architecture.

use std::alloc::Layout;
use std::ptr::NonNull;

/// The lowest-level allocator interface.
///
/// # Safety
/// Implementations must return properly aligned, non-overlapping memory
/// regions. Callers must ensure `dealloc` is called exactly once for each
/// successful `alloc`.
pub unsafe trait RawAllocator {
    /// Allocate memory with the given layout.
    ///
    /// Returns `None` if the backing memory is exhausted.
    unsafe fn alloc(&self, layout: Layout) -> Option<NonNull<u8>>;

    /// Deallocate memory previously returned by `alloc`.
    unsafe fn dealloc(&self, ptr: NonNull<u8>, layout: Layout);
}

/// Interface for fixed-size slab allocators.
///
/// All operations are O(1) and branch-predictor friendly.
pub trait SlabAlloc {
    /// Allocate one slot. Returns `None` if all chunks are full.
    fn alloc(&self) -> Option<NonNull<u8>>;

    /// Free a slot previously returned by `alloc`.
    ///
    /// # Safety
    /// `ptr` must have been allocated by this allocator and not already freed.
    unsafe fn free(&self, ptr: NonNull<u8>);

    /// Size of each slot in bytes.
    fn slot_size(&self) -> usize;

    /// Alignment of each slot.
    fn slot_align(&self) -> usize;

    /// Total number of slots across all chunks.
    fn total_slots(&self) -> usize;

    /// Number of currently free slots.
    fn free_slots(&self) -> usize;
}

/// Interface for bump-pointer arena allocators.
///
/// Individual objects cannot be freed; only the entire arena can be reset.
pub trait ArenaAlloc {
    /// Allocate `size` bytes with `align` alignment.
    ///
    /// Returns `None` if the arena does not have contiguous capacity.
    fn alloc(&self, size: usize, align: usize) -> Option<NonNull<u8>>;

    /// Reset the arena to empty. This is O(1) and invalidates all previous
    /// allocations.
    fn reset(&self);

    /// Bytes currently allocated in the arena.
    fn used(&self) -> usize;

    /// Total capacity in bytes.
    fn capacity(&self) -> usize;
}
''',

    "crates/memory/src/slab.rs": '''//! Slab Allocator
//!
//! Fixed-size object allocator using OS `mmap` for chunk backing memory and
//! a per-chunk bitmap for O(1) allocation/deallocation.
//!
//! ## Architecture
//! - Chunk memory is divided into a bitmap header and a data region.
//! - Bitmap bit `1` = free, `0` = used.
//! - Allocation scans the bitmap for the first set bit (free slot).
//! - Deallocation calculates the slot index from the pointer offset and sets
//!   the corresponding bit.
//!
//! ## Memory Layout of a Chunk
//! ```text
//! [ bitmap (N*8 bytes) | padding to slot_align | slot 0 | slot 1 | ... ]
//! ```
//!
//! ## Safety
//! This allocator is **not thread-safe**. All `alloc`/`free` calls must be
//! made from the owning thread, or the caller must provide external locking.

use std::cell::{Cell, UnsafeCell};
use std::ptr::NonNull;

use crate::traits::SlabAlloc;

/// Maximum slot size permitted by the specification: **1 KB**.
pub const MAX_SLAB_SLOT_SIZE: usize = 1024;

/// A slab allocator for fixed-size objects.
///
/// Backing memory is obtained via `mmap` (or `VirtualAlloc` on Windows).
/// No system `malloc`/`free` is called on the hot path.
pub struct SlabAllocator {
    slot_size: usize,
    slot_align: usize,
    slots_per_chunk: usize,
    chunk_size: usize,
    chunks: UnsafeCell<Vec<SlabChunk>>,
    current_chunk: Cell<usize>,
}

struct SlabChunk {
    base: NonNull<u8>,
    total_size: usize,
    bitmap_ptr: *mut u64,
    bitmap_words: usize,
    data_ptr: NonNull<u8>,
    free_count: usize,
}

unsafe impl Send for SlabAllocator {}

impl SlabAllocator {
    pub fn new(slot_size: usize, slot_align: usize, slots_per_chunk: usize) -> Option<Self> {
        debug_assert!(slot_size > 0);
        debug_assert!(slot_align.is_power_of_two());
        debug_assert!(slot_align <= 4096);
        if slot_size > MAX_SLAB_SLOT_SIZE {
            return None;
        }

        let bitmap_words = (slots_per_chunk + 63) / 64;
        let bitmap_size = bitmap_words.checked_mul(std::mem::size_of::<u64>())?;
        let data_offset = align_up(bitmap_size, slot_align);
        let data_size = slots_per_chunk.checked_mul(slot_size)?;
        let total_size = align_up(data_offset.checked_add(data_size)?, page_size());

        Some(Self {
            slot_size,
            slot_align,
            slots_per_chunk,
            chunk_size: total_size,
            chunks: UnsafeCell::new(Vec::new()),
            current_chunk: Cell::new(0),
        })
    }

    pub fn reserve_chunk(&self) -> bool {
        self.grow().is_some()
    }

    fn grow(&self) -> Option<&mut SlabChunk> {
        let chunks = unsafe { &mut *self.chunks.get() };
        let chunk = SlabChunk::new(self.chunk_size, self.slots_per_chunk, self.slot_size, self.slot_align)?;
        chunks.push(chunk);
        let idx = chunks.len() - 1;
        self.current_chunk.set(idx);
        Some(&mut chunks[idx])
    }

    fn find_free_chunk(&self) -> Option<(usize, &mut SlabChunk)> {
        let chunks = unsafe { &mut *self.chunks.get() };
        let n = chunks.len();
        if n == 0 {
            return None;
        }

        let start = self.current_chunk.get();
        for i in 0..n {
            let idx = (start + i) % n;
            let chunk = unsafe { chunks.get_unchecked_mut(idx) };
            if chunk.free_count > 0 {
                return Some((idx, chunk));
            }
        }
        None
    }
}

impl SlabAlloc for SlabAllocator {
    fn alloc(&self) -> Option<NonNull<u8>> {
        let (chunk_idx, chunk) = self.find_free_chunk().or_else(|| {
            self.grow().map(|c| (self.current_chunk.get(), c))
        })?;

        unsafe {
            let bitmap = std::slice::from_raw_parts_mut(chunk.bitmap_ptr, chunk.bitmap_words);
            for word_idx in 0..chunk.bitmap_words {
                let word = bitmap[word_idx];
                if word != 0 {
                    let bit_idx = word.trailing_zeros() as usize;
                    bitmap[word_idx] &= !(1u64 << bit_idx);
                    chunk.free_count -= 1;
                    self.current_chunk.set(chunk_idx);

                    let slot_idx = word_idx * 64 + bit_idx;
                    debug_assert!(slot_idx < self.slots_per_chunk);
                    let ptr = chunk.data_ptr.as_ptr().add(slot_idx * self.slot_size);
                    return Some(NonNull::new_unchecked(ptr));
                }
            }
        }

        unreachable!("SlabAllocator::alloc: free_count > 0 but bitmap exhausted")
    }

    unsafe fn free(&self, ptr: NonNull<u8>) {
        let chunks = &mut *self.chunks.get();
        for chunk in chunks.iter_mut() {
            let base = chunk.base.as_ptr();
            let end = base.add(chunk.total_size);
            let ptr_raw = ptr.as_ptr();

            if ptr_raw >= base && ptr_raw < end {
                let offset = ptr_raw.offset_from(chunk.data_ptr.as_ptr()) as usize;
                debug_assert!(offset % self.slot_size == 0);
                let slot_idx = offset / self.slot_size;
                debug_assert!(slot_idx < self.slots_per_chunk);

                let word_idx = slot_idx / 64;
                let bit_idx = slot_idx % 64;
                let bitmap = std::slice::from_raw_parts_mut(chunk.bitmap_ptr, chunk.bitmap_words);

                debug_assert!((bitmap[word_idx] >> bit_idx) & 1 == 0, "double free");

                bitmap[word_idx] |= 1u64 << bit_idx;
                chunk.free_count += 1;
                return;
            }
        }

        panic!("SlabAllocator::free: pointer does not belong to this allocator");
    }

    fn slot_size(&self) -> usize { self.slot_size }
    fn slot_align(&self) -> usize { self.slot_align }
    fn total_slots(&self) -> usize {
        let chunks = unsafe { &*self.chunks.get() };
        chunks.len() * self.slots_per_chunk
    }
    fn free_slots(&self) -> usize {
        let chunks = unsafe { &*self.chunks.get() };
        chunks.iter().map(|c| c.free_count).sum()
    }
}

impl Drop for SlabAllocator {
    fn drop(&mut self) {
        let chunks = unsafe { &mut *self.chunks.get() };
        chunks.clear();
    }
}

impl std::fmt::Debug for SlabAllocator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let chunks = unsafe { &*self.chunks.get() };
        f.debug_struct("SlabAllocator")
            .field("slot_size", &self.slot_size)
            .field("slot_align", &self.slot_align)
            .field("slots_per_chunk", &self.slots_per_chunk)
            .field("chunk_count", &chunks.len())
            .field("total_free_slots", &self.free_slots())
            .finish()
    }
}

impl SlabChunk {
    fn new(total_size: usize, slots_per_chunk: usize, slot_size: usize, slot_align: usize) -> Option<Self> {
        let total_size = align_up(total_size, page_size());
        let base = unsafe {
            let ptr = libc::mmap(
                std::ptr::null_mut(),
                total_size,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                -1,
                0,
            );
            if ptr == libc::MAP_FAILED {
                return None;
            }
            NonNull::new_unchecked(ptr as *mut u8)
        };

        let bitmap_words = (slots_per_chunk + 63) / 64;
        let bitmap_size = bitmap_words * std::mem::size_of::<u64>();
        let data_offset = align_up(bitmap_size, slot_align);

        unsafe {
            let bitmap = std::slice::from_raw_parts_mut(base.as_ptr() as *mut u64, bitmap_words);
            let valid_bits = slots_per_chunk;
            for i in 0..bitmap_words {
                let bits_in_this_word = 64usize.min(valid_bits.saturating_sub(i * 64));
                bitmap[i] = if bits_in_this_word == 64 { !0u64 } else { (1u64 << bits_in_this_word) - 1 };
            }
        }

        Some(Self {
            base,
            total_size,
            bitmap_ptr: base.as_ptr() as *mut u64,
            bitmap_words,
            data_ptr: NonNull::new(unsafe { base.as_ptr().add(data_offset) })?,
            free_count: slots_per_chunk,
        })
    }
}

impl Drop for SlabChunk {
    fn drop(&mut self) {
        unsafe { libc::munmap(self.base.as_ptr() as *mut libc::c_void, self.total_size); }
    }
}

#[inline(always)]
fn align_up(size: usize, align: usize) -> usize {
    debug_assert!(align.is_power_of_two());
    (size + align - 1) & !(align - 1)
}

fn page_size() -> usize {
    static PAGE_SIZE: std::sync::OnceLock<usize> = std::sync::OnceLock::new();
    *PAGE_SIZE.get_or_init(|| {
        #[cfg(unix)]
        unsafe { libc::sysconf(libc::_SC_PAGESIZE) as usize }
        #[cfg(target_os = "windows")]
        unsafe {
            let mut info: SYSTEM_INFO = std::mem::zeroed();
            GetSystemInfo(&mut info);
            info.dwPageSize as usize
        }
        #[cfg(not(any(unix, target_os = "windows")))]
        { 4096 }
    })
}

#[cfg(target_os = "windows")]
#[repr(C)]
struct SYSTEM_INFO {
    dwPageSize: u32,
    lpMinimumApplicationAddress: *mut libc::c_void,
    lpMaximumApplicationAddress: *mut libc::c_void,
    dwActiveProcessorMask: *mut libc::c_void,
    dwNumberOfProcessors: u32,
    dwProcessorType: u32,
    dwAllocationGranularity: u32,
    wProcessorLevel: u16,
    wProcessorRevision: u16,
}

#[cfg(target_os = "windows")]
extern "system" { fn GetSystemInfo(lpSystemInfo: *mut SYSTEM_INFO); }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slab_alloc_free_cycle() {
        let slab = SlabAllocator::new(64, 8, 128).expect("slab creation failed");
        let ptr = slab.alloc().expect("alloc failed");
        assert!(!ptr.as_ptr().is_null());
        unsafe { slab.free(ptr) };
        assert_eq!(slab.free_slots(), 128);
    }

    #[test]
    fn slab_chunk_growth() {
        let slab = SlabAllocator::new(32, 4, 4).expect("slab creation failed");
        let mut ptrs = Vec::new();
        for _ in 0..16 { ptrs.push(slab.alloc().expect("alloc failed")); }
        assert_eq!(slab.total_slots(), 16);
        for ptr in ptrs { unsafe { slab.free(ptr) }; }
        assert_eq!(slab.free_slots(), 16);
    }

    #[test]
    fn slab_oversized_rejected() {
        assert!(SlabAllocator::new(1025, 8, 16).is_none());
    }

    #[test]
    fn slab_bitmap_consistency() {
        let slab = SlabAllocator::new(16, 16, 70).expect("slab creation failed");
        let p1 = slab.alloc().expect("alloc 1");
        let p2 = slab.alloc().expect("alloc 2");
        unsafe { slab.free(p1) };
        unsafe { slab.free(p2) };
        assert_eq!(slab.free_slots(), 70);
    }
}
''',

    "crates/memory/src/arena.rs": '''//! Arena Allocator
//!
//! A bump-pointer allocator backed by a single `mmap`'d region. Objects are
//! allocated by advancing an offset. Individual objects cannot be freed;
//! only the entire arena can be reset in O(1).

use std::cell::Cell;
use std::ptr::NonNull;

use crate::traits::ArenaAlloc;

pub struct ArenaAllocator {
    base: NonNull<u8>,
    capacity: usize,
    offset: Cell<usize>,
}

unsafe impl Send for ArenaAllocator {}

impl ArenaAllocator {
    pub fn new(capacity: usize) -> Option<Self> {
        if capacity == 0 { return None; }
        let capacity = align_up(capacity, page_size());
        let base = unsafe {
            let ptr = libc::mmap(
                std::ptr::null_mut(),
                capacity,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                -1,
                0,
            );
            if ptr == libc::MAP_FAILED { return None; }
            NonNull::new_unchecked(ptr as *mut u8)
        };
        Some(Self { base, capacity, offset: Cell::new(0) })
    }

    #[inline]
    fn current_ptr(&self) -> *mut u8 {
        unsafe { self.base.as_ptr().add(self.offset.get()) }
    }
}

impl ArenaAlloc for ArenaAllocator {
    #[inline]
    fn alloc(&self, size: usize, align: usize) -> Option<NonNull<u8>> {
        if size == 0 {
            return Some(NonNull::new(self.current_ptr())?);
        }
        let align = align.max(1);
        debug_assert!(align.is_power_of_two());
        let offset = self.offset.get();
        let aligned = align_up(offset, align);
        let new_offset = aligned.checked_add(size)?;
        if new_offset > self.capacity { return None; }
        self.offset.set(new_offset);
        Some(unsafe { NonNull::new_unchecked(self.base.as_ptr().add(aligned)) })
    }

    #[inline]
    fn reset(&self) { self.offset.set(0); }
    #[inline]
    fn used(&self) -> usize { self.offset.get() }
    #[inline]
    fn capacity(&self) -> usize { self.capacity }
}

impl Drop for ArenaAllocator {
    fn drop(&mut self) {
        unsafe { libc::munmap(self.base.as_ptr() as *mut libc::c_void, self.capacity); }
    }
}

impl std::fmt::Debug for ArenaAllocator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ArenaAllocator")
            .field("capacity", &self.capacity)
            .field("used", &self.used())
            .field("free", &(self.capacity - self.used()))
            .finish()
    }
}

#[inline(always)]
fn align_up(size: usize, align: usize) -> usize {
    debug_assert!(align.is_power_of_two());
    (size + align - 1) & !(align - 1)
}

fn page_size() -> usize {
    static PAGE_SIZE: std::sync::OnceLock<usize> = std::sync::OnceLock::new();
    *PAGE_SIZE.get_or_init(|| {
        #[cfg(unix)]
        unsafe { libc::sysconf(libc::_SC_PAGESIZE) as usize }
        #[cfg(target_os = "windows")]
        unsafe {
            let mut info: SYSTEM_INFO = std::mem::zeroed();
            GetSystemInfo(&mut info);
            info.dwPageSize as usize
        }
        #[cfg(not(any(unix, target_os = "windows")))]
        { 4096 }
    })
}

#[cfg(target_os = "windows")]
#[repr(C)]
struct SYSTEM_INFO {
    dwPageSize: u32,
    lpMinimumApplicationAddress: *mut libc::c_void,
    lpMaximumApplicationAddress: *mut libc::c_void,
    dwActiveProcessorMask: *mut libc::c_void,
    dwNumberOfProcessors: u32,
    dwProcessorType: u32,
    dwAllocationGranularity: u32,
    wProcessorLevel: u16,
    wProcessorRevision: u16,
}

#[cfg(target_os = "windows")]
extern "system" { fn GetSystemInfo(lpSystemInfo: *mut SYSTEM_INFO); }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn arena_bump_and_reset() {
        let arena = ArenaAllocator::new(4096).expect("arena creation");
        let p1 = arena.alloc(100, 1).expect("alloc 1");
        let p2 = arena.alloc(50, 8).expect("alloc 2");
        assert_eq!(p2.as_ptr() as usize % 8, 0);
        assert_eq!(arena.used(), 152);
        arena.reset();
        assert_eq!(arena.used(), 0);
        let p3 = arena.alloc(200, 1).expect("alloc 3");
        assert_eq!(p3, p1);
    }

    #[test]
    fn arena_alignment() {
        let arena = ArenaAllocator::new(4096).unwrap();
        let p1 = arena.alloc(1, 64).expect("alloc 1");
        let p2 = arena.alloc(1, 64).expect("alloc 2");
        assert_eq!(p1.as_ptr() as usize % 64, 0);
        assert_eq!(p2.as_ptr() as usize % 64, 0);
        assert_eq!(p2.as_ptr() as usize - p1.as_ptr() as usize, 64);
    }

    #[test]
    fn arena_exhaustion() {
        let arena = ArenaAllocator::new(64).unwrap();
        assert!(arena.alloc(128, 1).is_none());
        assert!(arena.alloc(64, 1).is_some());
        assert!(arena.alloc(1, 1).is_none());
    }
}
''',

    "crates/memory/src/direct.rs": '''//! Direct OS Allocator
//!
//! For allocations exceeding the slab/arena thresholds (typically > 32 KB).
//! Each allocation is a standalone `mmap` (or `VirtualAlloc`) region returned
//! directly to the OS on deallocation.

use std::ptr::NonNull;

pub struct DirectAllocator;

impl DirectAllocator {
    pub fn alloc(&self, size: usize) -> Option<NonNull<u8>> {
        if size == 0 { return None; }
        let size = align_up(size, page_size());
        unsafe {
            let ptr = libc::mmap(
                std::ptr::null_mut(),
                size,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                -1,
                0,
            );
            if ptr == libc::MAP_FAILED { return None; }
            Some(NonNull::new_unchecked(ptr as *mut u8))
        }
    }

    pub unsafe fn dealloc(&self, ptr: NonNull<u8>, size: usize) {
        let size = align_up(size, page_size());
        libc::munmap(ptr.as_ptr() as *mut libc::c_void, size);
    }
}

impl Default for DirectAllocator { fn default() -> Self { Self } }

#[inline(always)]
fn align_up(size: usize, align: usize) -> usize {
    debug_assert!(align.is_power_of_two());
    (size + align - 1) & !(align - 1)
}

fn page_size() -> usize {
    static PAGE_SIZE: std::sync::OnceLock<usize> = std::sync::OnceLock::new();
    *PAGE_SIZE.get_or_init(|| {
        #[cfg(unix)]
        unsafe { libc::sysconf(libc::_SC_PAGESIZE) as usize }
        #[cfg(target_os = "windows")]
        unsafe {
            let mut info: SYSTEM_INFO = std::mem::zeroed();
            GetSystemInfo(&mut info);
            info.dwPageSize as usize
        }
        #[cfg(not(any(unix, target_os = "windows")))]
        { 4096 }
    })
}

#[cfg(target_os = "windows")]
#[repr(C)]
struct SYSTEM_INFO {
    dwPageSize: u32,
    lpMinimumApplicationAddress: *mut libc::c_void,
    lpMaximumApplicationAddress: *mut libc::c_void,
    dwActiveProcessorMask: *mut libc::c_void,
    dwNumberOfProcessors: u32,
    dwProcessorType: u32,
    dwAllocationGranularity: u32,
    wProcessorLevel: u16,
    wProcessorRevision: u16,
}

#[cfg(target_os = "windows")]
extern "system" { fn GetSystemInfo(lpSystemInfo: *mut SYSTEM_INFO); }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn direct_alloc_roundtrip() {
        let direct = DirectAllocator;
        let ptr = direct.alloc(1024).expect("direct alloc");
        assert!(!ptr.as_ptr().is_null());
        unsafe { direct.dealloc(ptr, 1024) };
    }

    #[test]
    fn direct_large_alloc() {
        let direct = DirectAllocator;
        let ptr = direct.alloc(10 * 1024 * 1024).expect("large alloc");
        unsafe { direct.dealloc(ptr, 10 * 1024 * 1024) };
    }
}
''',

    "crates/memory/src/tiered.rs": '''//! Tiered Allocator System
//!
//! The unified registry where each engine subsystem selects its dedicated
//! allocator.

use platform::CapabilityProfile;

use crate::arena::ArenaAllocator;
use crate::direct::DirectAllocator;
use crate::slab::SlabAllocator;

pub struct TieredAllocator {
    pub dom_node_slab: SlabAllocator,
    pub style_token_slab: SlabAllocator,
    pub network_packet_slab: SlabAllocator,
    pub small_bitmap_slab: SlabAllocator,
    pub parser_arena: ArenaAllocator,
    pub layout_arena: ArenaAllocator,
    pub direct: DirectAllocator,
}

impl TieredAllocator {
    pub fn new(profile: CapabilityProfile) -> Option<Self> {
        let (slab_slots, arena_cap) = match profile {
            CapabilityProfile::Embedded => (512, 256 * 1024),
            CapabilityProfile::Low => (1024, 1024 * 1024),
            CapabilityProfile::Standard => (4096, 4 * 1024 * 1024),
            CapabilityProfile::High => (16384, 16 * 1024 * 1024),
        };

        Some(Self {
            dom_node_slab: SlabAllocator::new(64, 8, slab_slots)?,
            style_token_slab: SlabAllocator::new(32, 4, slab_slots)?,
            network_packet_slab: SlabAllocator::new(1024, 8, slab_slots / 4)?,
            small_bitmap_slab: SlabAllocator::new(1024, 16, slab_slots / 4)?,
            parser_arena: ArenaAllocator::new(arena_cap)?,
            layout_arena: ArenaAllocator::new(arena_cap * 2)?,
            direct: DirectAllocator,
        })
    }

    pub fn warm(&self) {
        self.dom_node_slab.reserve_chunk();
        self.style_token_slab.reserve_chunk();
        self.network_packet_slab.reserve_chunk();
        self.small_bitmap_slab.reserve_chunk();
    }

    pub fn mapped_memory(&self) -> usize {
        let slab_chunks = 4;
        let page_size = page_size();
        let slab_size = slab_chunks * page_size;
        let arena_size = 3 * 16 * 1024 * 1024;
        slab_size + arena_size
    }
}

fn page_size() -> usize {
    static PAGE_SIZE: std::sync::OnceLock<usize> = std::sync::OnceLock::new();
    *PAGE_SIZE.get_or_init(|| {
        #[cfg(unix)]
        unsafe { libc::sysconf(libc::_SC_PAGESIZE) as usize }
        #[cfg(target_os = "windows")]
        unsafe {
            let mut info: SYSTEM_INFO = std::mem::zeroed();
            GetSystemInfo(&mut info);
            info.dwPageSize as usize
        }
        #[cfg(not(any(unix, target_os = "windows")))]
        { 4096 }
    })
}

#[cfg(target_os = "windows")]
#[repr(C)]
struct SYSTEM_INFO {
    dwPageSize: u32,
    lpMinimumApplicationAddress: *mut libc::c_void,
    lpMaximumApplicationAddress: *mut libc::c_void,
    dwActiveProcessorMask: *mut libc::c_void,
    dwNumberOfProcessors: u32,
    dwProcessorType: u32,
    dwAllocationGranularity: u32,
    wProcessorLevel: u16,
    wProcessorRevision: u16,
}

#[cfg(target_os = "windows")]
extern "system" { fn GetSystemInfo(lpSystemInfo: *mut SYSTEM_INFO); }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tiered_creation_all_profiles() {
        for profile in [
            CapabilityProfile::Embedded,
            CapabilityProfile::Low,
            CapabilityProfile::Standard,
            CapabilityProfile::High,
        ] {
            let tiered = TieredAllocator::new(profile).expect(&format!("{:?} failed", profile));
            assert!(tiered.dom_node_slab.total_slots() > 0);
            assert!(tiered.parser_arena.capacity() > 0);
        }
    }

    #[test]
    fn tiered_warm() {
        let tiered = TieredAllocator::new(CapabilityProfile::Standard).unwrap();
        tiered.warm();
        assert!(tiered.dom_node_slab.free_slots() > 0);
    }
}
''',

    "crates/memory/src/bench.rs": '''//! Allocator Benchmarks

use std::time::{Duration, Instant};

use crate::arena::ArenaAllocator;
use crate::slab::SlabAllocator;
use crate::traits::{ArenaAlloc, SlabAlloc};

#[derive(Debug, Clone)]
pub struct BenchmarkResult {
    pub name: &'static str,
    pub iterations: usize,
    pub total_time: Duration,
    pub ns_per_op: f64,
    pub ops_per_sec: f64,
}

impl BenchmarkResult {
    pub fn print(&self) {
        println!(
            "[{}] {} ops in {:?} | {:.2} ns/op | {:.2} ops/sec",
            self.name, self.iterations, self.total_time, self.ns_per_op, self.ops_per_sec
        );
    }
}

pub fn bench_slab(slab: &SlabAllocator, iterations: usize) -> BenchmarkResult {
    let mut ptrs = Vec::with_capacity(iterations);
    let start = Instant::now();
    for _ in 0..iterations { ptrs.push(slab.alloc().expect("slab OOM")); }
    for ptr in &ptrs { unsafe { slab.free(*ptr) }; }
    let elapsed = start.elapsed();
    BenchmarkResult {
        name: "slab_alloc_free",
        iterations,
        total_time: elapsed,
        ns_per_op: elapsed.as_nanos() as f64 / iterations as f64,
        ops_per_sec: iterations as f64 / elapsed.as_secs_f64(),
    }
}

pub fn bench_arena(arena: &ArenaAllocator, iterations: usize, alloc_size: usize) -> BenchmarkResult {
    let start = Instant::now();
    for _ in 0..iterations { let _ = arena.alloc(alloc_size, 8); }
    let elapsed = start.elapsed();
    BenchmarkResult {
        name: "arena_bump",
        iterations,
        total_time: elapsed,
        ns_per_op: elapsed.as_nanos() as f64 / iterations as f64,
        ops_per_sec: iterations as f64 / elapsed.as_secs_f64(),
    }
}

pub fn bench_arena_reset(arena: &ArenaAllocator, iterations: usize) -> BenchmarkResult {
    let start = Instant::now();
    for _ in 0..iterations { arena.reset(); }
    let elapsed = start.elapsed();
    BenchmarkResult {
        name: "arena_reset",
        iterations,
        total_time: elapsed,
        ns_per_op: elapsed.as_nanos() as f64 / iterations as f64,
        ops_per_sec: iterations as f64 / elapsed.as_secs_f64(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bench_slab_smoke() {
        let slab = SlabAllocator::new(64, 8, 1024).unwrap();
        let result = bench_slab(&slab, 100_000);
        assert!(result.ns_per_op < 100.0, "slab too slow: {:.2} ns/op", result.ns_per_op);
    }

    #[test]
    fn bench_arena_smoke() {
        let arena = ArenaAllocator::new(16 * 1024 * 1024).unwrap();
        let result = bench_arena(&arena, 1_000_000, 32);
        assert!(result.ns_per_op < 50.0, "arena too slow: {:.2} ns/op", result.ns_per_op);
    }

    #[test]
    fn bench_arena_reset_smoke() {
        let arena = ArenaAllocator::new(1024 * 1024).unwrap();
        let result = bench_arena_reset(&arena, 1_000_000);
        assert!(result.ns_per_op < 10.0, "reset too slow: {:.2} ns/op", result.ns_per_op);
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 3: DOM
    # -------------------------------------------------------------------------
    "crates/dom/Cargo.toml": '''[package]
name = "dom"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
bitflags = "2.5"
memory = { path = "../memory" }
platform = { path = "../platform" }
''',

    "crates/dom/src/lib.rs": '''//! # Compact Flat Arena DOM
//!
//! A Structure-of-Arrays (SoA) DOM implementation where every node is a dense
//! `u32` index into parallel vectors.

pub mod arena_dom;
pub mod interner;
pub mod tree_ops;

pub use arena_dom::{Attribute, AttributeList, FlatArenaDOM, NodeFlags, NodeId};
pub use interner::{InternedString, StringInterner};
pub use tree_ops::{Ancestors, Children, Descendants};
''',

    "crates/dom/src/interner.rs": '''//! String Interning

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub struct InternedString(pub u32);

impl InternedString {
    pub const NONE: Self = Self(u32::MAX);
}

#[derive(Debug, Clone)]
pub struct StringInterner {
    strings: Vec<Box<str>>,
    index: HashMap<Box<str>, u32>,
}

impl StringInterner {
    pub fn new() -> Self {
        Self { strings: Vec::new(), index: HashMap::new() }
    }

    pub fn intern(&mut self, s: &str) -> InternedString {
        if let Some(&idx) = self.index.get(s) {
            return InternedString(idx);
        }
        let idx = self.strings.len() as u32;
        let owned: Box<str> = s.into();
        self.index.insert(owned.clone(), idx);
        self.strings.push(owned);
        InternedString(idx)
    }

    pub fn resolve(&self, handle: InternedString) -> Option<&str> {
        self.strings.get(handle.0 as usize).map(|s| s.as_ref())
    }

    pub fn len(&self) -> usize { self.strings.len() }
    pub fn is_empty(&self) -> bool { self.strings.is_empty() }
}

impl Default for StringInterner { fn default() -> Self { Self::new() } }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn intern_deduplicates() {
        let mut interner = StringInterner::new();
        let a = interner.intern("div");
        let b = interner.intern("div");
        let c = interner.intern("span");
        assert_eq!(a, b);
        assert_ne!(a, c);
        assert_eq!(interner.len(), 2);
    }

    #[test]
    fn resolve_roundtrip() {
        let mut interner = StringInterner::new();
        let h = interner.intern("hello");
        assert_eq!(interner.resolve(h), Some("hello"));
    }
}
''',

    "crates/dom/src/arena_dom.rs": '''//! FlatArenaDOM — Structure of Arrays DOM

use crate::interner::InternedString;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct NodeId(u32);

impl NodeId {
    pub const NONE: Self = Self(u32::MAX);
    pub const DOCUMENT: Self = Self(0);
    pub const fn new(index: u32) -> Self { Self(index) }
    pub const fn index(self) -> usize { self.0 as usize }
    pub const fn is_none(self) -> bool { self.0 == u32::MAX }
    pub const fn is_some(self) -> bool { !self.is_none() }
}

impl Default for NodeId { fn default() -> Self { Self::NONE } }

bitflags::bitflags! {
    #[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
    pub struct NodeFlags: u32 {
        const IS_ELEMENT  = 1 << 0;
        const IS_TEXT     = 1 << 1;
        const IS_DIRTY    = 1 << 2;
        const IS_VISIBLE  = 1 << 3;
        const IS_FOCUSED  = 1 << 4;
        const IS_COMMENT  = 1 << 5;
        const IS_DOCUMENT = 1 << 6;
        const IS_DOCTYPE  = 1 << 7;
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct AttributeList {
    pub start: u32,
    pub count: u32,
}

impl AttributeList {
    pub const EMPTY: Self = Self { start: 0, count: 0 };
    pub fn is_empty(self) -> bool { self.count == 0 }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Attribute {
    pub name: InternedString,
    pub value: InternedString,
}

pub struct FlatArenaDOM {
    pub parent: Vec<NodeId>,
    pub first_child: Vec<NodeId>,
    pub next_sibling: Vec<NodeId>,
    pub prev_sibling: Vec<NodeId>,
    pub last_child: Vec<NodeId>,
    pub flags: Vec<NodeFlags>,
    pub style_index: Vec<u32>,
    pub text_index: Vec<InternedString>,
    pub local_name: Vec<InternedString>,
    pub namespace: Vec<InternedString>,
    pub attrs: Vec<AttributeList>,
    pub attr_buffer: Vec<Attribute>,
    free_list: Vec<NodeId>,
    len: usize,
}

impl FlatArenaDOM {
    pub fn new() -> Self {
        let mut dom = Self {
            parent: Vec::new(), first_child: Vec::new(), next_sibling: Vec::new(),
            prev_sibling: Vec::new(), last_child: Vec::new(), flags: Vec::new(),
            style_index: Vec::new(), text_index: Vec::new(), local_name: Vec::new(),
            namespace: Vec::new(), attrs: Vec::new(), attr_buffer: Vec::new(),
            free_list: Vec::new(), len: 0,
        };
        let doc = dom.create_node(NodeFlags::IS_DOCUMENT);
        assert_eq!(doc, NodeId::DOCUMENT);
        dom
    }

    pub fn with_capacity(capacity: usize) -> Self {
        let mut dom = Self {
            parent: Vec::with_capacity(capacity),
            first_child: Vec::with_capacity(capacity),
            next_sibling: Vec::with_capacity(capacity),
            prev_sibling: Vec::with_capacity(capacity),
            last_child: Vec::with_capacity(capacity),
            flags: Vec::with_capacity(capacity),
            style_index: Vec::with_capacity(capacity),
            text_index: Vec::with_capacity(capacity),
            local_name: Vec::with_capacity(capacity),
            namespace: Vec::with_capacity(capacity),
            attrs: Vec::with_capacity(capacity),
            attr_buffer: Vec::with_capacity(capacity * 4),
            free_list: Vec::new(),
            len: 0,
        };
        let doc = dom.create_node(NodeFlags::IS_DOCUMENT);
        assert_eq!(doc, NodeId::DOCUMENT);
        dom
    }

    pub fn len(&self) -> usize { self.len }
    pub fn is_empty(&self) -> bool { self.len <= 1 }
    pub fn free_slots(&self) -> usize { self.free_list.len() }

    pub fn create_node(&mut self, flags: NodeFlags) -> NodeId {
        if let Some(id) = self.free_list.pop() {
            let idx = id.index();
            self.flags[idx] = flags;
            self.parent[idx] = NodeId::NONE;
            self.first_child[idx] = NodeId::NONE;
            self.next_sibling[idx] = NodeId::NONE;
            self.prev_sibling[idx] = NodeId::NONE;
            self.last_child[idx] = NodeId::NONE;
            self.style_index[idx] = 0;
            self.text_index[idx] = InternedString::NONE;
            self.local_name[idx] = InternedString::NONE;
            self.namespace[idx] = InternedString::NONE;
            self.attrs[idx] = AttributeList::EMPTY;
            id
        } else {
            let id = NodeId::new(self.len as u32);
            self.parent.push(NodeId::NONE);
            self.first_child.push(NodeId::NONE);
            self.next_sibling.push(NodeId::NONE);
            self.prev_sibling.push(NodeId::NONE);
            self.last_child.push(NodeId::NONE);
            self.flags.push(flags);
            self.style_index.push(0);
            self.text_index.push(InternedString::NONE);
            self.local_name.push(InternedString::NONE);
            self.namespace.push(InternedString::NONE);
            self.attrs.push(AttributeList::EMPTY);
            self.len += 1;
            id
        }
    }

    pub fn create_element_node(
        &mut self,
        local_name: InternedString,
        namespace: InternedString,
        attributes: &[Attribute],
        flags: NodeFlags,
    ) -> NodeId {
        let id = self.create_node(flags | NodeFlags::IS_ELEMENT);
        let idx = id.index();
        self.local_name[idx] = local_name;
        self.namespace[idx] = namespace;
        self.set_attributes(id, attributes);
        id
    }

    pub fn create_text_node(&mut self, text: InternedString) -> NodeId {
        let id = self.create_node(NodeFlags::IS_TEXT);
        self.text_index[id.index()] = text;
        id
    }

    pub fn create_comment_node(&mut self, text: InternedString) -> NodeId {
        let id = self.create_node(NodeFlags::IS_COMMENT);
        self.text_index[id.index()] = text;
        id
    }

    pub fn create_pi_node(&mut self, data: InternedString) -> NodeId {
        let id = self.create_node(NodeFlags::empty());
        self.text_index[id.index()] = data;
        id
    }

    pub fn create_doctype_node(&mut self, name: InternedString) -> NodeId {
        let id = self.create_node(NodeFlags::IS_DOCTYPE);
        self.text_index[id.index()] = name;
        id
    }

    pub fn set_attributes(&mut self, node: NodeId, attributes: &[Attribute]) {
        let start = self.attr_buffer.len() as u32;
        let count = attributes.len() as u32;
        self.attr_buffer.extend_from_slice(attributes);
        self.attrs[node.index()] = AttributeList { start, count };
    }

    pub fn get_attributes(&self, node: NodeId) -> &[Attribute] {
        let list = self.attrs[node.index()];
        if list.is_empty() { return &[]; }
        let start = list.start as usize;
        let end = (list.start + list.count) as usize;
        &self.attr_buffer[start..end]
    }

    pub fn append_child(&mut self, parent: NodeId, child: NodeId) {
        assert!(parent.is_some(), "invalid parent");
        assert!(child.is_some(), "invalid child");
        let child_idx = child.index();
        assert!(self.parent[child_idx].is_none(), "child already has parent");
        self.parent[child_idx] = parent;
        let parent_idx = parent.index();
        let last = self.last_child[parent_idx];
        if last.is_some() {
            self.next_sibling[last.index()] = child;
            self.prev_sibling[child_idx] = last;
        } else {
            self.first_child[parent_idx] = child;
        }
        self.last_child[parent_idx] = child;
        self.mark_dirty(parent);
    }

    pub fn insert_before(&mut self, sibling: NodeId, new_node: NodeId) {
        assert!(sibling.is_some(), "invalid sibling");
        assert!(new_node.is_some(), "invalid new_node");
        let sibling_idx = sibling.index();
        let parent = self.parent[sibling_idx];
        assert!(parent.is_some(), "sibling must have a parent");
        let new_idx = new_node.index();
        assert!(self.parent[new_idx].is_none(), "new_node already has a parent");
        let prev = self.prev_sibling[sibling_idx];
        self.parent[new_idx] = parent;
        self.next_sibling[new_idx] = sibling;
        self.prev_sibling[new_idx] = prev;
        if prev.is_some() {
            self.next_sibling[prev.index()] = new_node;
        } else {
            self.first_child[parent.index()] = new_node;
        }
        self.prev_sibling[sibling_idx] = new_node;
        self.mark_dirty(parent);
    }

    pub fn remove_node(&mut self, node: NodeId) {
        let node_idx = node.index();
        let parent = self.parent[node_idx];
        if parent.is_none() { return; }
        let prev = self.prev_sibling[node_idx];
        let next = self.next_sibling[node_idx];
        if prev.is_some() {
            self.next_sibling[prev.index()] = next;
        } else {
            self.first_child[parent.index()] = next;
        }
        if next.is_some() {
            self.prev_sibling[next.index()] = prev;
        } else {
            self.last_child[parent.index()] = prev;
        }
        self.parent[node_idx] = NodeId::NONE;
        self.next_sibling[node_idx] = NodeId::NONE;
        self.prev_sibling[node_idx] = NodeId::NONE;
        self.free_list.push(node);
        self.mark_dirty(parent);
    }

    pub fn reparent_children(&mut self, node: NodeId, new_parent: NodeId) {
        let node_idx = node.index();
        let child = self.first_child[node_idx];
        if child.is_none() { return; }
        let new_parent_idx = new_parent.index();
        let last = self.last_child[new_parent_idx];
        if last.is_some() {
            self.next_sibling[last.index()] = child;
            self.prev_sibling[child.index()] = last;
        } else {
            self.first_child[new_parent_idx] = child;
        }
        let mut current = child;
        while current.is_some() {
            self.parent[current.index()] = new_parent;
            current = self.next_sibling[current.index()];
        }
        self.last_child[new_parent_idx] = self.last_child[node_idx];
        self.first_child[node_idx] = NodeId::NONE;
        self.last_child[node_idx] = NodeId::NONE;
        self.mark_dirty(new_parent);
        self.mark_dirty(node);
    }

    pub fn mark_dirty(&mut self, node: NodeId) {
        let mut current = node;
        while current.is_some() {
            let idx = current.index();
            if self.flags[idx].contains(NodeFlags::IS_DIRTY) { break; }
            self.flags[idx] |= NodeFlags::IS_DIRTY;
            current = self.parent[idx];
        }
    }

    pub fn clear_dirty(&mut self, node: NodeId) {
        self.flags[node.index()].remove(NodeFlags::IS_DIRTY);
    }

    pub fn clear_all_dirty(&mut self) {
        for flags in &mut self.flags { flags.remove(NodeFlags::IS_DIRTY); }
    }

    pub fn clear(&mut self) {
        self.len = 1;
        self.free_list.clear();
        self.attr_buffer.clear();
        self.parent[0] = NodeId::NONE;
        self.first_child[0] = NodeId::NONE;
        self.next_sibling[0] = NodeId::NONE;
        self.prev_sibling[0] = NodeId::NONE;
        self.last_child[0] = NodeId::NONE;
        self.flags[0] = NodeFlags::IS_DOCUMENT;
        self.style_index[0] = 0;
        self.text_index[0] = InternedString::NONE;
        self.local_name[0] = InternedString::NONE;
        self.namespace[0] = InternedString::NONE;
        self.attrs[0] = AttributeList::EMPTY;
    }
}

impl Default for FlatArenaDOM { fn default() -> Self { Self::new() } }

impl std::fmt::Debug for FlatArenaDOM {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("FlatArenaDOM")
            .field("len", &self.len)
            .field("capacity", &self.parent.capacity())
            .field("free_slots", &self.free_slots())
            .finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dom_document_root() {
        let dom = FlatArenaDOM::new();
        assert_eq!(dom.len(), 1);
        assert!(dom.flags[0].contains(NodeFlags::IS_DOCUMENT));
    }

    #[test]
    fn dom_append_and_topology() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        let b = dom.create_node(NodeFlags::IS_ELEMENT);
        let c = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.append_child(NodeId::DOCUMENT, b);
        dom.append_child(NodeId::DOCUMENT, c);
        assert_eq!(dom.first_child[0], a);
        assert_eq!(dom.next_sibling[a.index()], b);
        assert_eq!(dom.next_sibling[b.index()], c);
        assert_eq!(dom.last_child[0], c);
        assert_eq!(dom.prev_sibling[c.index()], b);
    }

    #[test]
    fn dom_insert_before() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        let b = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.insert_before(a, b);
        assert_eq!(dom.first_child[0], b);
        assert_eq!(dom.next_sibling[b.index()], a);
        assert_eq!(dom.prev_sibling[a.index()], b);
    }

    #[test]
    fn dom_remove_node() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        let b = dom.create_node(NodeFlags::IS_ELEMENT);
        let c = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.append_child(NodeId::DOCUMENT, b);
        dom.append_child(NodeId::DOCUMENT, c);
        dom.remove_node(b);
        assert_eq!(dom.next_sibling[a.index()], c);
        assert_eq!(dom.prev_sibling[c.index()], a);
        assert_eq!(dom.free_slots(), 1);
    }

    #[test]
    fn dom_reparent_children() {
        let mut dom = FlatArenaDOM::new();
        let parent = dom.create_node(NodeFlags::IS_ELEMENT);
        let child = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(parent, child);
        dom.append_child(NodeId::DOCUMENT, parent);
        let new_parent = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, new_parent);
        dom.reparent_children(parent, new_parent);
        assert!(dom.first_child[parent.index()].is_none());
        assert_eq!(dom.first_child[new_parent.index()], child);
        assert_eq!(dom.parent[child.index()], new_parent);
    }

    #[test]
    fn dom_dirty_propagation() {
        let mut dom = FlatArenaDOM::new();
        let child = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, child);
        dom.clear_all_dirty();
        dom.mark_dirty(child);
        assert!(dom.flags[0].contains(NodeFlags::IS_DIRTY));
    }

    #[test]
    fn dom_node_reuse() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.remove_node(a);
        let b = dom.create_node(NodeFlags::IS_TEXT);
        assert_eq!(a, b);
        assert!(dom.parent[b.index()].is_none());
    }

    #[test]
    fn dom_attributes() {
        let mut dom = FlatArenaDOM::new();
        let node = dom.create_node(NodeFlags::IS_ELEMENT);
        let attrs = [
            Attribute { name: InternedString(0), value: InternedString(1) },
            Attribute { name: InternedString(2), value: InternedString(3) },
        ];
        dom.set_attributes(node, &attrs);
        let retrieved = dom.get_attributes(node);
        assert_eq!(retrieved.len(), 2);
        assert_eq!(retrieved[0].name, InternedString(0));
        assert_eq!(retrieved[1].value, InternedString(3));
    }
}
''',

    "crates/dom/src/tree_ops.rs": '''//! Tree Traversal

use crate::arena_dom::{FlatArenaDOM, NodeId};

pub struct Children<'a> {
    dom: &'a FlatArenaDOM,
    current: NodeId,
}

impl<'a> Children<'a> {
    pub fn new(dom: &'a FlatArenaDOM, parent: NodeId) -> Self {
        Self { dom, current: dom.first_child[parent.index()] }
    }
}

impl<'a> Iterator for Children<'a> {
    type Item = NodeId;
    fn next(&mut self) -> Option<Self::Item> {
        if self.current.is_none() { return None; }
        let node = self.current;
        self.current = self.dom.next_sibling[node.index()];
        Some(node)
    }
}

pub struct Ancestors<'a> {
    dom: &'a FlatArenaDOM,
    current: NodeId,
}

impl<'a> Ancestors<'a> {
    pub fn new(dom: &'a FlatArenaDOM, node: NodeId) -> Self {
        Self { dom, current: dom.parent[node.index()] }
    }
}

impl<'a> Iterator for Ancestors<'a> {
    type Item = NodeId;
    fn next(&mut self) -> Option<Self::Item> {
        if self.current.is_none() { return None; }
        let node = self.current;
        self.current = self.dom.parent[node.index()];
        Some(node)
    }
}

pub struct Descendants<'a> {
    dom: &'a FlatArenaDOM,
    stack: Vec<NodeId>,
}

impl<'a> Descendants<'a> {
    pub fn new(dom: &'a FlatArenaDOM, root: NodeId) -> Self {
        let mut stack = Vec::new();
        if root.is_some() { stack.push(root); }
        Self { dom, stack }
    }
}

impl<'a> Iterator for Descendants<'a> {
    type Item = NodeId;
    fn next(&mut self) -> Option<Self::Item> {
        let node = self.stack.pop()?;
        let mut child = self.dom.first_child[node.index()];
        while child.is_some() {
            self.stack.push(child);
            child = self.dom.next_sibling[child.index()];
        }
        Some(node)
    }
}

impl FlatArenaDOM {
    pub fn children(&self, node: NodeId) -> Children { Children::new(self, node) }
    pub fn ancestors(&self, node: NodeId) -> Ancestors { Ancestors::new(self, node) }
    pub fn descendants(&self, node: NodeId) -> Descendants { Descendants::new(self, node) }

    pub fn for_each_child<F>(&self, node: NodeId, mut f: F)
    where
        F: FnMut(NodeId),
    {
        let mut child = self.first_child[node.index()];
        while child.is_some() {
            f(child);
            child = self.next_sibling[child.index()];
        }
    }

    pub fn traverse_preorder<F>(&self, root: NodeId, mut f: F)
    where
        F: FnMut(NodeId),
    {
        let mut stack = [NodeId::NONE; 256];
        let mut sp = 0;
        stack[sp] = root;
        sp += 1;

        while sp > 0 {
            sp -= 1;
            let current = stack[sp];
            if current.is_none() { continue; }
            f(current);
            let mut children = [NodeId::NONE; 32];
            let mut count = 0;
            let mut child = self.first_child[current.index()];
            while child.is_some() && count < children.len() {
                children[count] = child;
                count += 1;
                child = self.next_sibling[child.index()];
            }
            for i in (0..count).rev() {
                if sp < stack.len() {
                    stack[sp] = children[i];
                    sp += 1;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::arena_dom::{FlatArenaDOM, NodeFlags};

    #[test]
    fn iter_children() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        let b = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.append_child(NodeId::DOCUMENT, b);
        let collected: Vec<_> = dom.children(NodeId::DOCUMENT).collect();
        assert_eq!(collected, vec![a, b]);
    }

    #[test]
    fn iter_ancestors() {
        let mut dom = FlatArenaDOM::new();
        let p = dom.create_node(NodeFlags::IS_ELEMENT);
        let c = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, p);
        dom.append_child(p, c);
        let collected: Vec<_> = dom.ancestors(c).collect();
        assert_eq!(collected, vec![p, NodeId::DOCUMENT]);
    }

    #[test]
    fn iter_descendants() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        let b = dom.create_node(NodeFlags::IS_ELEMENT);
        let c = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.append_child(a, b);
        dom.append_child(a, c);
        let collected: Vec<_> = dom.descendants(NodeId::DOCUMENT).collect();
        assert_eq!(collected, vec![NodeId::DOCUMENT, a, b, c]);
    }

    #[test]
    fn traverse_preorder_callback() {
        let mut dom = FlatArenaDOM::new();
        let a = dom.create_node(NodeFlags::IS_ELEMENT);
        let b = dom.create_node(NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.append_child(a, b);
        let mut visited = Vec::new();
        dom.traverse_preorder(NodeId::DOCUMENT, |n| visited.push(n));
        assert_eq!(visited, vec![NodeId::DOCUMENT, a, b]);
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 4: HTML
    # -------------------------------------------------------------------------
    "crates/html/Cargo.toml": '''[package]
name = "html"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
dom = { path = "../dom" }
memory = { path = "../memory" }
platform = { path = "../platform" }
html5ever = "0.27"
markup5ever = "0.12"
tendril = "0.4"
''',

    "crates/html/src/lib.rs": '''//! # HTML Parser
//!
//! Direct integration of `html5ever` with `FlatArenaDOM`.

pub mod parser;
pub use parser::parse_html;
''',

    "crates/html/src/parser.rs": '''//! HTML5 TreeSink Implementation

use std::collections::HashMap;

use dom::arena_dom::{FlatArenaDOM, NodeFlags, NodeId};
use dom::interner::{InternedString, StringInterner};

use html5ever::tree_builder::{ElementFlags, NodeOrText, QuirksMode, TreeSink};
use html5ever::{Attribute, QualName};
use markup5ever::{ExpandedName, LocalName, Namespace};
use tendril::StrTendril;

pub struct HtmlTreeSink<'a> {
    dom: &'a mut FlatArenaDOM,
    interner: &'a mut StringInterner,
    quirks_mode: QuirksMode,
    local_name_cache: HashMap<InternedString, LocalName>,
    namespace_cache: HashMap<InternedString, Namespace>,
}

impl<'a> HtmlTreeSink<'a> {
    pub fn new(dom: &'a mut FlatArenaDOM, interner: &'a mut StringInterner) -> Self {
        Self {
            dom,
            interner,
            quirks_mode: QuirksMode::NoQuirks,
            local_name_cache: HashMap::new(),
            namespace_cache: HashMap::new(),
        }
    }

    fn append_text_to_parent(&mut self, parent: NodeId, text: &str) {
        let last_child = self.dom.last_child[parent.index()];
        if last_child.is_some()
            && self.dom.flags[last_child.index()].contains(NodeFlags::IS_TEXT)
        {
            let existing = self.interner.resolve(self.dom.text_index[last_child.index()]).unwrap_or("");
            let combined = format!("{}{}", existing, text);
            let interned = self.interner.intern(&combined);
            self.dom.text_index[last_child.index()] = interned;
        } else {
            let interned = self.interner.intern(text);
            let text_node = self.dom.create_text_node(interned);
            self.dom.append_child(parent, text_node);
        }
    }

    fn append_text_before_sibling(&mut self, sibling: NodeId, text: &str) {
        let prev = self.dom.prev_sibling[sibling.index()];
        if prev.is_some() && self.dom.flags[prev.index()].contains(NodeFlags::IS_TEXT) {
            let existing = self.interner.resolve(self.dom.text_index[prev.index()]).unwrap_or("");
            let combined = format!("{}{}", existing, text);
            let interned = self.interner.intern(&combined);
            self.dom.text_index[prev.index()] = interned;
        } else {
            let interned = self.interner.intern(text);
            let text_node = self.dom.create_text_node(interned);
            self.dom.insert_before(sibling, text_node);
        }
    }
}

impl<'a> TreeSink for HtmlTreeSink<'a> {
    type Handle = NodeId;
    type Output = ();

    fn finish(self) -> Self::Output {}

    fn parse_error(&mut self, msg: std::borrow::Cow<'static, str>) {
        #[cfg(debug_assertions)]
        eprintln!("HTML parse error: {}", msg);
    }

    fn get_document(&mut self) -> Self::Handle { NodeId::DOCUMENT }

    fn elem_name(&self, target: &Self::Handle) -> ExpandedName {
        let idx = target.index();
        let local = self.local_name_cache.get(&self.dom.local_name[idx]).expect("local name not cached").clone();
        let ns = self.namespace_cache.get(&self.dom.namespace[idx]).expect("namespace not cached").clone();
        ExpandedName { ns, local }
    }

    fn same_node(&self, x: &Self::Handle, y: &Self::Handle) -> bool { x == y }

    fn create_element(
        &mut self,
        name: QualName,
        attrs: Vec<Attribute>,
        _flags: ElementFlags,
    ) -> Self::Handle {
        let local_str: &str = &name.local;
        let ns_str: &str = &name.ns;
        let interned_local = self.interner.intern(local_str);
        let interned_ns = self.interner.intern(ns_str);
        self.local_name_cache.insert(interned_local, name.local.clone());
        self.namespace_cache.insert(interned_ns, name.ns.clone());

        let dom_attrs: Vec<dom::Attribute> = attrs.into_iter().map(|attr| dom::Attribute {
            name: self.interner.intern(&attr.name.local),
            value: self.interner.intern(&attr.value),
        }).collect();

        self.dom.create_element_node(interned_local, interned_ns, &dom_attrs, NodeFlags::IS_ELEMENT)
    }

    fn create_comment(&mut self, text: StrTendril) -> Self::Handle {
        let interned = self.interner.intern(&text);
        self.dom.create_comment_node(interned)
    }

    fn create_pi(&mut self, _target: StrTendril, data: StrTendril) -> Self::Handle {
        let interned = self.interner.intern(&data);
        self.dom.create_pi_node(interned)
    }

    fn append(&mut self, parent: &Self::Handle, child: NodeOrText<Self::Handle>) {
        match child {
            NodeOrText::AppendNode(node) => { self.dom.append_child(*parent, node); }
            NodeOrText::AppendText(text) => { self.append_text_to_parent(*parent, &text); }
        }
    }

    fn append_before_sibling(
        &mut self,
        sibling: &Self::Handle,
        child: NodeOrText<Self::Handle>,
    ) {
        match child {
            NodeOrText::AppendNode(node) => { self.dom.insert_before(*sibling, node); }
            NodeOrText::AppendText(text) => { self.append_text_before_sibling(*sibling, &text); }
        }
    }

    fn append_based_on_parent_node(
        &mut self,
        element: &Self::Handle,
        prev_element: &Self::Handle,
        child: NodeOrText<Self::Handle>,
    ) {
        if self.dom.parent[element.index()].is_some() {
            self.append(element, child);
        } else {
            self.append_before_sibling(prev_element, child);
        }
    }

    fn append_doctype_to_document(
        &mut self,
        name: StrTendril,
        _public_id: StrTendril,
        _system_id: StrTendril,
    ) {
        let name_interned = self.interner.intern(&name);
        let doctype = self.dom.create_doctype_node(name_interned);
        self.dom.append_child(NodeId::DOCUMENT, doctype);
    }

    fn remove_from_parent(&mut self, target: &Self::Handle) {
        self.dom.remove_node(*target);
    }

    fn reparent_children(&mut self, node: &Self::Handle, new_parent: &Self::Handle) {
        self.dom.reparent_children(*node, *new_parent);
    }

    fn mark_script_already_started(&mut self, _node: &Self::Handle) {}

    fn pop(&mut self, _node: &Self::Handle) {}

    fn set_quirks_mode(&mut self, mode: QuirksMode) {
        self.quirks_mode = mode;
    }
}

pub fn parse_html(dom: &mut FlatArenaDOM, interner: &mut StringInterner, html: &str) {
    let sink = HtmlTreeSink::new(dom, interner);
    let opts = html5ever::driver::ParseOpts::default();
    let input: StrTendril = html.into();
    let _ = html5ever::driver::parse_document(sink, opts).one(input);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_simple_document() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        parse_html(&mut dom, &mut interner, "<!DOCTYPE html><html><body><p>Hello</p></body></html>");
        assert!(dom.len() > 1);
        let html_node = dom.first_child[NodeId::DOCUMENT.index()];
        assert!(html_node.is_some());
        let name = interner.resolve(dom.local_name[html_node.index()]);
        assert_eq!(name, Some("html"));
    }

    #[test]
    fn parse_text_coalescing() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        parse_html(&mut dom, &mut interner, "<p>Hello</p>");
        let p = dom.first_child[NodeId::DOCUMENT.index()];
        assert!(p.is_some());
        let text = dom.first_child[p.index()];
        assert!(text.is_some());
        assert!(dom.flags[text.index()].contains(NodeFlags::IS_TEXT));
        let content = interner.resolve(dom.text_index[text.index()]);
        assert_eq!(content, Some("Hello"));
    }

    #[test]
    fn parse_attributes() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        parse_html(&mut dom, &mut interner, r#"<div class="foo" id="bar"></div>"#);
        let div = dom.first_child[NodeId::DOCUMENT.index()];
        let attrs = dom.get_attributes(div);
        assert_eq!(attrs.len(), 2);
        assert_eq!(interner.resolve(attrs[0].name), Some("class"));
        assert_eq!(interner.resolve(attrs[0].value), Some("foo"));
        assert_eq!(interner.resolve(attrs[1].name), Some("id"));
        assert_eq!(interner.resolve(attrs[1].value), Some("bar"));
    }

    #[test]
    fn parse_nested_structure() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        parse_html(&mut dom, &mut interner, "<html><head></head><body><div><span>text</span></div></body></html>");
        let html = dom.first_child[NodeId::DOCUMENT.index()];
        assert!(html.is_some());
        let mut found_span = false;
        dom.traverse_preorder(NodeId::DOCUMENT, |node| {
            if interner.resolve(dom.local_name[node.index()]) == Some("span") { found_span = true; }
        });
        assert!(found_span);
    }

    #[test]
    fn parse_comment() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        parse_html(&mut dom, &mut interner, "<!-- comment -->");
        let comment = dom.first_child[NodeId::DOCUMENT.index()];
        assert!(comment.is_some());
        assert!(dom.flags[comment.index()].contains(NodeFlags::IS_COMMENT));
        assert_eq!(interner.resolve(dom.text_index[comment.index()]), Some(" comment "));
    }

    #[test]
    fn parse_doctype() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        parse_html(&mut dom, &mut interner, "<!DOCTYPE html>");
        let doctype = dom.first_child[NodeId::DOCUMENT.index()];
        assert!(doctype.is_some());
        assert!(dom.flags[doctype.index()].contains(NodeFlags::IS_DOCTYPE));
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 5: JavaScript
    # -------------------------------------------------------------------------
    "crates/javascript/Cargo.toml": '''[package]
name = "javascript"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
dom = { path = "../dom" }
memory = { path = "../memory" }
platform = { path = "../platform" }
libc = "0.2"
''',

    "crates/javascript/src/lib.rs": '''//! # JavaScript Subsystem
//!
//! QuickJS integration with zero-allocation native DOM bindings, fetch bridge,
//! and persistent bytecode cache.

pub mod bytecode_cache;
pub mod dom_bindings;
pub mod fetch_bridge;
pub mod qjs_ffi;
pub mod runtime;

pub use runtime::{JsEngine, JsError, JsValue};
''',

    "crates/javascript/src/qjs_ffi.rs": '''//! Raw FFI bindings to the QuickJS C API.

use libc::{c_char, c_int, c_void, size_t};

#[repr(C)]
pub struct JSRuntime { _private: [u8; 0], }

#[repr(C)]
pub struct JSContext { _private: [u8; 0], }

pub type JSValue = u64;
pub type JSClassID = u32;
pub type JSAtom = u32;

pub const JS_EVAL_TYPE_GLOBAL: c_int = 0;
pub const JS_EVAL_TYPE_MODULE: c_int = 1;
pub const JS_EVAL_FLAG_COMPILE_ONLY: c_int = 1 << 3;
pub const JS_READ_OBJ_BYTECODE: c_int = 1;
pub const JS_WRITE_OBJ_BYTECODE: c_int = 1;
pub const JS_PROP_C_W_E: c_int = 0xF;

#[repr(C)]
pub struct JSClassDef {
    pub class_name: *const c_char,
    pub finalizer: Option<unsafe extern "C" fn(*mut JSRuntime, JSValue)>,
    pub gc_mark: Option<unsafe extern "C" fn(*mut JSRuntime, JSValue, *mut c_void)>,
    pub call: Option<unsafe extern "C" fn(*mut JSContext, JSValue, JSValue, c_int, *mut JSValue, c_int) -> JSValue>,
    pub exotic: *mut c_void,
}

#[repr(C)]
pub struct JSPropertyEnum {
    pub is_enumerable: c_int,
    pub atom: JSAtom,
}

extern "C" {
    pub fn JS_NewRuntime() -> *mut JSRuntime;
    pub fn JS_FreeRuntime(rt: *mut JSRuntime);
    pub fn JS_SetMemoryLimit(rt: *mut JSRuntime, limit: size_t);
    pub fn JS_SetGCThreshold(rt: *mut JSRuntime, threshold: size_t);
    pub fn JS_RunGC(rt: *mut JSRuntime);
    pub fn JS_NewContext(rt: *mut JSRuntime) -> *mut JSContext;
    pub fn JS_FreeContext(ctx: *mut JSContext);
    pub fn JS_GetContextOpaque(ctx: *mut JSContext) -> *mut c_void;
    pub fn JS_SetContextOpaque(ctx: *mut JSContext, opaque: *mut c_void);
    pub fn JS_AddIntrinsicBaseObjects(ctx: *mut JSContext);
    pub fn JS_AddIntrinsicDate(ctx: *mut JSContext);
    pub fn JS_AddIntrinsicEval(ctx: *mut JSContext);
    pub fn JS_AddIntrinsicJSON(ctx: *mut JSContext);
    pub fn JS_AddIntrinsicPromise(ctx: *mut JSContext);
    pub fn JS_AddIntrinsicTypedArrays(ctx: *mut JSContext);
    pub fn JS_AddIntrinsicBigInt(ctx: *mut JSContext);
    pub fn JS_Eval(ctx: *mut JSContext, input: *const c_char, input_len: size_t, filename: *const c_char, eval_flags: c_int) -> JSValue;
    pub fn JS_GetException(ctx: *mut JSContext) -> JSValue;
    pub fn JS_IsException(val: JSValue) -> c_int;
    pub fn JS_IsUndefined(val: JSValue) -> c_int;
    pub fn JS_IsNull(val: JSValue) -> c_int;
    pub fn JS_IsString(val: JSValue) -> c_int;
    pub fn JS_IsNumber(val: JSValue) -> c_int;
    pub fn JS_IsObject(val: JSValue) -> c_int;
    pub fn JS_IsArray(ctx: *mut JSContext, val: JSValue) -> c_int;
    pub fn JS_IsFunction(ctx: *mut JSContext, val: JSValue) -> c_int;
    pub fn JS_ToInt32(ctx: *mut JSContext, pres: *mut c_int, val: JSValue) -> c_int;
    pub fn JS_ToInt64(ctx: *mut JSContext, pres: *mut i64, val: JSValue) -> c_int;
    pub fn JS_ToFloat64(ctx: *mut JSContext, pres: *mut f64, val: JSValue) -> c_int;
    pub fn JS_ToCStringLen2(ctx: *mut JSContext, plen: *mut size_t, val: JSValue, cesu8: c_int) -> *const c_char;
    pub fn JS_FreeCString(ctx: *mut JSContext, ptr: *const c_char);
    pub fn JS_NewObject(ctx: *mut JSContext) -> JSValue;
    pub fn JS_NewObjectProto(ctx: *mut JSContext, proto: JSValue) -> JSValue;
    pub fn JS_NewStringLen(ctx: *mut JSContext, str: *const c_char, len1: size_t) -> JSValue;
    pub fn JS_NewInt32(ctx: *mut JSContext, val: c_int) -> JSValue;
    pub fn JS_NewInt64(ctx: *mut JSContext, val: i64) -> JSValue;
    pub fn JS_NewFloat64(ctx: *mut JSContext, d: f64) -> JSValue;
    pub fn JS_NewBool(ctx: *mut JSContext, val: c_int) -> JSValue;
    pub fn JS_GetGlobalObject(ctx: *mut JSContext) -> JSValue;
    pub fn JS_GetPropertyStr(ctx: *mut JSContext, this_obj: JSValue, prop: *const c_char) -> JSValue;
    pub fn JS_SetPropertyStr(ctx: *mut JSContext, this_obj: JSValue, prop: *const c_char, val: JSValue) -> c_int;
    pub fn JS_GetPropertyUint32(ctx: *mut JSContext, this_obj: JSValue, idx: u32) -> JSValue;
    pub fn JS_SetPropertyUint32(ctx: *mut JSContext, this_obj: JSValue, idx: u32, val: JSValue) -> c_int;
    pub fn JS_DefinePropertyValueStr(ctx: *mut JSContext, this_obj: JSValue, prop: *const c_char, val: JSValue, flags: c_int) -> c_int;
    pub fn JS_DefinePropertyValueUint32(ctx: *mut JSContext, this_obj: JSValue, idx: u32, val: JSValue, flags: c_int) -> c_int;
    pub fn JS_Call(ctx: *mut JSContext, func_obj: JSValue, this_obj: JSValue, argc: c_int, argv: *mut JSValue) -> JSValue;
    pub fn JS_CallConstructor(ctx: *mut JSContext, func_obj: JSValue, argc: c_int, argv: *mut JSValue) -> JSValue;
    pub fn JS_FreeValue(ctx: *mut JSContext, v: JSValue);
    pub fn JS_FreeValueRT(rt: *mut JSRuntime, v: JSValue);
    pub fn JS_DupValue(ctx: *mut JSContext, v: JSValue) -> JSValue;
    pub fn JS_DupValueRT(rt: *mut JSRuntime, v: JSValue) -> JSValue;
    pub fn JS_NewClassID(pclass_id: *mut JSClassID) -> JSClassID;
    pub fn JS_NewClass(rt: *mut JSRuntime, class_id: JSClassID, class_def: *const JSClassDef) -> c_int;
    pub fn JS_SetClassProto(ctx: *mut JSContext, class_id: JSClassID, obj: JSValue);
    pub fn JS_GetClassProto(ctx: *mut JSContext, class_id: JSClassID) -> JSValue;
    pub fn JS_GetOpaque(obj: JSValue, class_id: JSClassID) -> *mut c_void;
    pub fn JS_GetOpaque2(ctx: *mut JSContext, obj: JSValue, class_id: JSClassID) -> *mut c_void;
    pub fn JS_SetOpaque(obj: JSValue, opaque: *mut c_void);
    pub fn JS_ReadObject(ctx: *mut JSContext, buf: *const u8, buf_len: size_t, flags: c_int) -> JSValue;
    pub fn JS_WriteObject(ctx: *mut JSContext, psize: *mut size_t, obj: JSValue, flags: c_int) -> *mut u8;
    pub fn JS_GetOwnPropertyNames(ctx: *mut JSContext, ptab: *mut *mut JSPropertyEnum, plen: *mut u32, obj: JSValue, flags: c_int) -> c_int;
    pub fn JS_FreeAtom(ctx: *mut JSContext, atom: JSAtom);
    pub fn JS_AtomToString(ctx: *mut JSContext, atom: JSAtom) -> JSValue;
    pub fn JS_AtomToCString(ctx: *mut JSContext, atom: JSAtom) -> *const c_char;
    pub fn JS_NewPromiseCapability(ctx: *mut JSContext, resolving_funcs: *mut JSValue) -> JSValue;
}
''',

    "crates/javascript/src/runtime.rs": '''//! Safe wrapper around the QuickJS runtime and context.

use std::ffi::{CStr, CString};
use std::ptr::NonNull;

use dom::arena_dom::{FlatArenaDOM, NodeId};
use dom::interner::StringInterner;

use crate::bytecode_cache::BytecodeCache;
use crate::dom_bindings::DOM_NODE_CLASS_ID;
use crate::fetch_bridge::FetchBridge;
use crate::qjs_ffi::*;

pub struct JsEngine {
    rt: *mut JSRuntime,
    ctx: *mut JSContext,
    _marker: std::marker::PhantomData<*mut ()>,
}

pub struct JsValue {
    raw: JSValue,
    ctx: *mut JSContext,
}

impl Drop for JsValue {
    fn drop(&mut self) {
        unsafe { JS_FreeValue(self.ctx, self.raw) }
    }
}

impl JsValue {
    pub fn raw(&self) -> JSValue { self.raw }
}

#[derive(Debug, Clone)]
pub enum JsError {
    Eval(String),
    Internal(&'static str),
}

pub struct JsContextState {
    pub dom: *mut FlatArenaDOM,
    pub interner: *mut StringInterner,
    pub fetch_bridge: FetchBridge,
    pub bytecode_cache: BytecodeCache,
}

impl JsEngine {
    pub fn new() -> Option<Self> {
        unsafe {
            let rt = JS_NewRuntime();
            if rt.is_null() { return None; }
            JS_SetMemoryLimit(rt, 64 * 1024 * 1024);
            JS_SetGCThreshold(rt, 1024 * 1024);
            let ctx = JS_NewContext(rt);
            if ctx.is_null() {
                JS_FreeRuntime(rt);
                return None;
            }
            JS_AddIntrinsicBaseObjects(ctx);
            JS_AddIntrinsicDate(ctx);
            JS_AddIntrinsicEval(ctx);
            JS_AddIntrinsicJSON(ctx);
            JS_AddIntrinsicPromise(ctx);
            JS_AddIntrinsicTypedArrays(ctx);
            JS_AddIntrinsicBigInt(ctx);
            let mut engine = Self { rt, ctx, _marker: std::marker::PhantomData };
            engine.register_dom_class()?;
            Some(engine)
        }
    }

    pub fn attach_dom(
        &mut self,
        dom: &mut FlatArenaDOM,
        interner: &mut StringInterner,
        cache_dir: std::path::PathBuf,
    ) {
        let state = Box::new(JsContextState {
            dom,
            interner,
            fetch_bridge: FetchBridge::new(),
            bytecode_cache: BytecodeCache::new(cache_dir),
        });
        unsafe { JS_SetContextOpaque(self.ctx, Box::into_raw(state) as *mut c_void); }
    }

    pub fn eval(&mut self, script: &str, url: Option<&str>) -> Result<JsValue, JsError> {
        unsafe {
            if let Some(url) = url {
                let state = JS_GetContextOpaque(self.ctx) as *mut JsContextState;
                if !state.is_null() {
                    if let Some(obj) = (*state).bytecode_cache.load(url, self.ctx) {
                        let global = JS_GetGlobalObject(self.ctx);
                        let ret = JS_Call(self.ctx, obj, global, 0, std::ptr::null_mut());
                        JS_FreeValue(self.ctx, global);
                        JS_FreeValue(self.ctx, obj);
                        if JS_IsException(ret) != 0 {
                            JS_FreeValue(self.ctx, ret);
                            return Err(self.capture_exception());
                        }
                        return Ok(JsValue { raw: ret, ctx: self.ctx });
                    }
                }
            }

            let c_script = CString::new(script).map_err(|_| JsError::Internal("nul in script"))?;
            let c_name = CString::new(url.unwrap_or("<eval>")).map_err(|_| JsError::Internal("nul in filename"))?;
            let val = JS_Eval(self.ctx, c_script.as_ptr(), c_script.as_bytes().len(), c_name.as_ptr(), JS_EVAL_TYPE_GLOBAL);

            if JS_IsException(val) != 0 {
                JS_FreeValue(self.ctx, val);
                return Err(self.capture_exception());
            }

            if let Some(url) = url {
                let state = JS_GetContextOpaque(self.ctx) as *mut JsContextState;
                if !state.is_null() {
                    let _ = (*state).bytecode_cache.store(url, self.ctx, val);
                }
            }

            Ok(JsValue { raw: val, ctx: self.ctx })
        }
    }

    pub fn poll_fetch(&mut self) {
        unsafe {
            let state = JS_GetContextOpaque(self.ctx) as *mut JsContextState;
            if state.is_null() { return; }
            (*state).fetch_bridge.poll(self.ctx);
        }
    }

    pub fn run_gc(&self) { unsafe { JS_RunGC(self.rt) } }

    fn capture_exception(&self) -> JsError {
        unsafe {
            let exc = JS_GetException(self.ctx);
            let msg = js_value_to_string(self.ctx, exc).unwrap_or_default();
            JS_FreeValue(self.ctx, exc);
            JsError::Eval(msg)
        }
    }

    fn register_dom_class(&mut self) -> Option<()> {
        crate::dom_bindings::register(self.ctx)
    }
}

impl Drop for JsEngine {
    fn drop(&mut self) {
        unsafe {
            let opaque = JS_GetContextOpaque(self.ctx);
            if !opaque.is_null() { drop(Box::from_raw(opaque as *mut JsContextState)); }
            JS_FreeContext(self.ctx);
            JS_FreeRuntime(self.rt);
        }
    }
}

pub unsafe fn js_value_to_string(ctx: *mut JSContext, val: JSValue) -> Option<String> {
    let mut len = 0usize;
    let ptr = JS_ToCStringLen2(ctx, &mut len, val, 0);
    if ptr.is_null() { return None; }
    let s = CStr::from_ptr(ptr).to_string_lossy().into_owned();
    JS_FreeCString(ctx, ptr);
    Some(s)
}

pub unsafe fn js_value_to_node_id(ctx: *mut JSContext, val: JSValue) -> Option<NodeId> {
    let ptr = JS_GetOpaque2(ctx, val, DOM_NODE_CLASS_ID);
    if ptr.is_null() { return None; }
    Some(*(ptr as *mut NodeId))
}

pub unsafe fn node_id_to_js_value(ctx: *mut JSContext, node: NodeId) -> JSValue {
    let proto = JS_GetClassProto(ctx, DOM_NODE_CLASS_ID);
    let obj = JS_NewObjectProto(ctx, proto);
    JS_FreeValue(ctx, proto);
    let boxed = Box::new(node);
    JS_SetOpaque(obj, Box::into_raw(boxed) as *mut c_void);
    obj
}
''',

    "crates/javascript/src/dom_bindings.rs": '''//! Native DOM bindings

use std::ffi::CString;

use dom::arena_dom::{FlatArenaDOM, NodeFlags, NodeId};
use dom::interner::StringInterner;

use crate::qjs_ffi::*;
use crate::runtime::{js_value_to_node_id, js_value_to_string, node_id_to_js_value, JsContextState};

pub static mut DOM_NODE_CLASS_ID: JSClassID = 0;

unsafe extern "C" fn dom_node_finalizer(_rt: *mut JSRuntime, val: JSValue) {
    let ptr = JS_GetOpaque(val, DOM_NODE_CLASS_ID);
    if !ptr.is_null() { drop(Box::from_raw(ptr as *mut NodeId)); }
}

pub fn register(ctx: *mut JSContext) -> Option<()> {
    unsafe {
        let mut class_id = 0u32;
        JS_NewClassID(&mut class_id);
        DOM_NODE_CLASS_ID = class_id;
        let name = CString::new("DOMNode").ok()?;
        let def = JSClassDef {
            class_name: name.as_ptr(),
            finalizer: Some(dom_node_finalizer),
            gc_mark: None,
            call: None,
            exotic: std::ptr::null_mut(),
        };
        if JS_NewClass(JS_GetContextOpaque(ctx) as *mut JSRuntime, class_id, &def) != 0 {
            return None;
        }
        let proto = JS_NewObject(ctx);
        define_method(ctx, proto, "appendChild", js_append_child);
        define_method(ctx, proto, "removeChild", js_remove_child);
        define_method(ctx, proto, "insertBefore", js_insert_before);
        define_method(ctx, proto, "getElementById", js_get_element_by_id);
        define_method(ctx, proto, "getElementsByTagName", js_get_elements_by_tag_name);
        define_method(ctx, proto, "setAttribute", js_set_attribute);
        define_method(ctx, proto, "getAttribute", js_get_attribute);
        JS_SetClassProto(ctx, class_id, proto);
        Some(())
    }
}

unsafe fn define_method(
    ctx: *mut JSContext,
    proto: JSValue,
    name: &str,
    func: unsafe extern "C" fn(*mut JSContext, JSValue, c_int, *mut JSValue, c_int) -> JSValue,
) {
    let c_name = CString::new(name).unwrap();
    let func_val = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, proto, c_name.as_ptr(), func_val);
}

unsafe extern "C" fn js_append_child(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 1 { return JS_EXCEPTION; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let parent = js_value_to_node_id(ctx, this_val);
    let child = js_value_to_node_id(ctx, *argv);
    if let (Some(p), Some(c)) = (parent, child) {
        (*state).dom.append_child(p, c);
        JS_DupValue(ctx, *argv)
    } else { JS_EXCEPTION }
}

unsafe extern "C" fn js_remove_child(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 1 { return JS_EXCEPTION; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let _parent = js_value_to_node_id(ctx, this_val);
    let child = js_value_to_node_id(ctx, *argv);
    if let (Some(_p), Some(c)) = (_parent, child) {
        (*state).dom.remove_node(c);
        JS_DupValue(ctx, *argv)
    } else { JS_EXCEPTION }
}

unsafe extern "C" fn js_insert_before(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 2 { return JS_EXCEPTION; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let _parent = js_value_to_node_id(ctx, this_val);
    let new_node = js_value_to_node_id(ctx, *argv);
    let reference = js_value_to_node_id(ctx, *argv.offset(1));
    if let (Some(_p), Some(n), Some(r)) = (_parent, new_node, reference) {
        (*state).dom.insert_before(r, n);
        JS_DupValue(ctx, *argv)
    } else { JS_EXCEPTION }
}

unsafe extern "C" fn js_get_element_by_id(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 1 { return JS_NULL; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let id = js_value_to_string(ctx, *argv).unwrap_or_default();
    let id_interned = (*state).interner.intern(&id);
    let mut found = None;
    (*state).dom.traverse_preorder(NodeId::DOCUMENT, |node| {
        if found.is_some() { return; }
        let attrs = (*state).dom.get_attributes(node);
        for attr in attrs {
            if (*state).interner.resolve(attr.name) == Some("id") && attr.value == id_interned {
                found = Some(node);
            }
        }
    });
    if let Some(node) = found { node_id_to_js_value(ctx, node) } else { JS_NULL }
}

unsafe extern "C" fn js_get_elements_by_tag_name(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 1 { return JS_EXCEPTION; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let tag = js_value_to_string(ctx, *argv).unwrap_or_default();
    let tag_interned = (*state).interner.intern(&tag);
    let mut nodes = Vec::new();
    (*state).dom.traverse_preorder(NodeId::DOCUMENT, |node| {
        if (*state).dom.flags[node.index()].contains(NodeFlags::IS_ELEMENT)
            && (*state).dom.local_name[node.index()] == tag_interned
        {
            nodes.push(node);
        }
    });
    let arr = JS_NewObject(ctx);
    for (i, node) in nodes.iter().enumerate() {
        let val = node_id_to_js_value(ctx, *node);
        JS_SetPropertyUint32(ctx, arr, i as u32, val);
    }
    arr
}

unsafe extern "C" fn js_set_attribute(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 2 { return JS_EXCEPTION; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let node = js_value_to_node_id(ctx, this_val);
    let name = js_value_to_string(ctx, *argv).unwrap_or_default();
    let value = js_value_to_string(ctx, *argv.offset(1)).unwrap_or_default();
    if let Some(n) = node {
        let name_i = (*state).interner.intern(&name);
        let value_i = (*state).interner.intern(&value);
        let attrs = [dom::arena_dom::Attribute { name: name_i, value: value_i }];
        (*state).dom.set_attributes(n, &attrs);
    }
    JS_UNDEFINED
}

unsafe extern "C" fn js_get_attribute(
    ctx: *mut JSContext, this_val: JSValue, argc: c_int, argv: *mut JSValue, _magic: c_int
) -> JSValue {
    if argc < 1 { return JS_NULL; }
    let state = JS_GetContextOpaque(ctx) as *mut JsContextState;
    if state.is_null() { return JS_EXCEPTION; }
    let node = js_value_to_node_id(ctx, this_val);
    let name = js_value_to_string(ctx, *argv).unwrap_or_default();
    if let Some(n) = node {
        let attrs = (*state).dom.get_attributes(n);
        for attr in attrs {
            if (*state).interner.resolve(attr.name) == Some(&name) {
                if let Some(val) = (*state).interner.resolve(attr.value) {
                    let c_val = CString::new(val).unwrap();
                    return JS_NewStringLen(ctx, c_val.as_ptr(), val.len());
                }
            }
        }
    }
    JS_NULL
}
''',

    "crates/javascript/src/fetch_bridge.rs": '''//! Fetch Bridge

use std::collections::HashMap;

use crate::qjs_ffi::*;

pub struct FetchBridge {
    next_id: u64,
    pending: HashMap<u64, PendingFetch>,
}

pub struct PendingFetch {
    pub promise: JSValue,
    pub resolve: JSValue,
    pub reject: JSValue,
    pub url: String,
}

impl FetchBridge {
    pub fn new() -> Self {
        Self { next_id: 1, pending: HashMap::new() }
    }

    pub fn next_id(&mut self) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    pub fn push(&mut self, fetch: PendingFetch) {
        self.pending.insert(self.next_id - 1, fetch);
    }

    pub fn poll(&mut self, ctx: *mut JSContext) {
        let _ = ctx;
    }

    pub unsafe fn resolve(&mut self, ctx: *mut JSContext, id: u64, data: &str) {
        if let Some(fetch) = self.pending.remove(&id) {
            let c_data = std::ffi::CString::new(data).unwrap();
            let val = JS_NewStringLen(ctx, c_data.as_ptr(), data.len());
            let mut args = [val];
            let _ = JS_Call(ctx, fetch.resolve, JS_UNDEFINED, 1, args.as_mut_ptr());
            JS_FreeValue(ctx, val);
            JS_FreeValue(ctx, fetch.resolve);
            JS_FreeValue(ctx, fetch.reject);
            JS_FreeValue(ctx, fetch.promise);
        }
    }

    pub unsafe fn reject(&mut self, ctx: *mut JSContext, id: u64, error: &str) {
        if let Some(fetch) = self.pending.remove(&id) {
            let c_err = std::ffi::CString::new(error).unwrap();
            let val = JS_NewStringLen(ctx, c_err.as_ptr(), error.len());
            let mut args = [val];
            let _ = JS_Call(ctx, fetch.reject, JS_UNDEFINED, 1, args.as_mut_ptr());
            JS_FreeValue(ctx, val);
            JS_FreeValue(ctx, fetch.resolve);
            JS_FreeValue(ctx, fetch.reject);
            JS_FreeValue(ctx, fetch.promise);
        }
    }
}

impl Default for FetchBridge {
    fn default() -> Self { Self::new() }
}
''',

    "crates/javascript/src/bytecode_cache.rs": '''//! Bytecode Cache

use std::path::PathBuf;

use crate::qjs_ffi::*;

pub struct BytecodeCache {
    dir: PathBuf,
}

impl BytecodeCache {
    pub fn new(dir: PathBuf) -> Self {
        std::fs::create_dir_all(&dir).ok();
        Self { dir }
    }

    pub fn key(url: &str) -> String {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        url.hash(&mut hasher);
        format!("{:x}.qbc", hasher.finish())
    }

    pub unsafe fn load(&self, url: &str, ctx: *mut JSContext) -> Option<JSValue> {
        let path = self.dir.join(Self::key(url));
        let data = std::fs::read(path).ok()?;
        let obj = JS_ReadObject(ctx, data.as_ptr(), data.len(), JS_READ_OBJ_BYTECODE);
        if JS_IsException(obj) != 0 {
            JS_FreeValue(ctx, obj);
            None
        } else {
            Some(obj)
        }
    }

    pub unsafe fn store(&self, url: &str, ctx: *mut JSContext, obj: JSValue) -> std::io::Result<()> {
        let mut len = 0usize;
        let ptr = JS_WriteObject(ctx, &mut len, obj, JS_WRITE_OBJ_BYTECODE);
        if ptr.is_null() {
            return Err(std::io::Error::new(std::io::ErrorKind::Other, "JS_WriteObject failed"));
        }
        let slice = std::slice::from_raw_parts(ptr, len);
        let path = self.dir.join(Self::key(url));
        std::fs::write(&path, slice)?;
        libc::free(ptr as *mut libc::c_void);
        Ok(())
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 6: CSS
    # -------------------------------------------------------------------------
    "crates/css/Cargo.toml": '''[package]
name = "css"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
dom = { path = "../dom" }
memory = { path = "../memory" }
platform = { path = "../platform" }
lightningcss = "1.0.0-alpha.57"
rayon = "1.10"
ahash = "0.8"
''',

    "crates/css/src/lib.rs": '''//! # CSS Subsystem
//!
//! lightningcss parsing, Selector Trie, Bloom Filter, Computed Style Cache,
//! and adaptive parallel matching.

pub mod bloom;
pub mod computed_style;
pub mod matching;
pub mod parser;
pub mod selector_trie;

pub use computed_style::{ComputedStyle, ComputedStyleCache};
pub use matching::MatchingEngine;
pub use parser::CssStylesheet;
pub use selector_trie::SelectorTrie;
''',

    "crates/css/src/parser.rs": '''//! CSS Parser Integration

use dom::interner::{InternedString, StringInterner};

use lightningcss::properties::Property;
use lightningcss::rules::CssRule;
use lightningcss::selector::{Combinator, Component};
use lightningcss::stylesheet::{ParserOptions, StyleSheet};

use crate::computed_style::{Color, ComputedStyle, Display, Float, Length, Position, TextAlign, Visibility};
use crate::selector_trie::{Selector, SelectorComponent};

#[derive(Debug, Clone)]
pub struct CssStylesheet {
    pub rules: Vec<StyleRule>,
}

#[derive(Debug, Clone)]
pub struct StyleRule {
    pub selectors: Vec<Selector>,
    pub declarations: Vec<Declaration>,
    pub specificity: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Declaration {
    pub property: PropertyName,
    pub value: DeclValue,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PropertyName {
    Display, Position, Float, Width, Height,
    MarginTop, MarginRight, MarginBottom, MarginLeft,
    PaddingTop, PaddingRight, PaddingBottom, PaddingLeft,
    Color, BackgroundColor, FontSize, FontFamily,
    TextAlign, Visibility, ZIndex, Unknown,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum DeclValue {
    Display(Display),
    Position(Position),
    Float(Float),
    Length(Length),
    Color(Color),
    TextAlign(TextAlign),
    Visibility(Visibility),
    ZIndex(i32),
    String(InternedString),
    None,
}

impl CssStylesheet {
    pub fn parse(css: &str, interner: &mut StringInterner) -> Result<Self, String> {
        let options = ParserOptions::default();
        let sheet = StyleSheet::parse(css, options).map_err(|e| e.to_string())?;
        let mut rules = Vec::new();
        for rule in &sheet.rules.0 {
            if let CssRule::Style(style) = rule {
                let mut selectors = Vec::new();
                for sel in &style.selectors.0 {
                    let mut comps = Vec::new();
                    for component in sel.iter() {
                        match component {
                            Component::ID(id) => comps.push(SelectorComponent::Id(interner.intern(id))),
                            Component::Class(class) => comps.push(SelectorComponent::Class(interner.intern(class))),
                            Component::LocalName(name) => comps.push(SelectorComponent::Tag(interner.intern(&name.name))),
                            Component::ExplicitUniversalNamespace | Component::ExplicitAnyNamespace => {
                                comps.push(SelectorComponent::Universal);
                            }
                            Component::Combinator(c) => {
                                comps.push(match c {
                                    Combinator::Descendant => SelectorComponent::Descendant,
                                    Combinator::Child => SelectorComponent::Child,
                                    Combinator::NextSibling => SelectorComponent::NextSibling,
                                    Combinator::LaterSibling => SelectorComponent::LaterSibling,
                                    _ => continue,
                                });
                            }
                            _ => {}
                        }
                    }
                    selectors.push(Selector { components: comps });
                }
                let mut declarations = Vec::new();
                for decl in &style.declarations.declarations {
                    if let Some(d) = convert_property(decl, interner) { declarations.push(d); }
                }
                rules.push(StyleRule { selectors, declarations, specificity: 0 });
            }
        }
        Ok(Self { rules })
    }
}

fn convert_property(property: &Property, interner: &mut StringInterner) -> Option<Declaration> {
    use lightningcss::properties::Property::*;
    match property {
        Display(display, _) => {
            use lightningcss::properties::display::Display::*;
            let val = match display {
                None | Contents => DeclValue::Display(Display::None),
                Block => DeclValue::Display(Display::Block),
                Inline => DeclValue::Display(Display::Inline),
                InlineBlock => DeclValue::Display(Display::InlineBlock),
                Flex(_) => DeclValue::Display(Display::Flex),
                Grid(_) => DeclValue::Display(Display::Grid),
                Table => DeclValue::Display(Display::Table),
                TableCell => DeclValue::Display(Display::TableCell),
                ListItem => DeclValue::Display(Display::ListItem),
                _ => DeclValue::Display(Display::Block),
            };
            Some(Declaration { property: PropertyName::Display, value: val })
        }
        Position(position, _) => {
            Some(Declaration { property: PropertyName::Position, value: DeclValue::Position(Position::Static) })
        }
        Width(width) => Some(Declaration { property: PropertyName::Width, value: convert_length(width) }),
        Height(height) => Some(Declaration { property: PropertyName::Height, value: convert_length(height) }),
        Margin(margin, _) => Some(Declaration { property: PropertyName::MarginTop, value: convert_length(&margin.top) }),
        Padding(padding, _) => Some(Declaration { property: PropertyName::PaddingTop, value: convert_length(&padding.top) }),
        Color(color) => Some(Declaration { property: PropertyName::Color, value: convert_color(color) }),
        BackgroundColor(color) => Some(Declaration { property: PropertyName::BackgroundColor, value: convert_color(color) }),
        FontSize(size, _) => Some(Declaration { property: PropertyName::FontSize, value: convert_length(size) }),
        TextAlign(align, _) => {
            use lightningcss::properties::text::TextAlign;
            let val = match align {
                TextAlign::Left => TextAlign::Left,
                TextAlign::Right => TextAlign::Right,
                TextAlign::Center => TextAlign::Center,
                TextAlign::Justify => TextAlign::Justify,
                _ => TextAlign::Start,
            };
            Some(Declaration { property: PropertyName::TextAlign, value: DeclValue::TextAlign(val) })
        }
        Visibility(vis, _) => {
            use lightningcss::properties::display::Visibility;
            let val = match vis {
                Visibility::Visible => Visibility::Visible,
                Visibility::Hidden => Visibility::Hidden,
                Visibility::Collapse => Visibility::Collapse,
            };
            Some(Declaration { property: PropertyName::Visibility, value: DeclValue::Visibility(val) })
        }
        ZIndex(z, _) => Some(Declaration { property: PropertyName::ZIndex, value: DeclValue::ZIndex(z.value()) }),
        _ => None,
    }
}

fn convert_length(len: &lightningcss::values::length::Length) -> DeclValue {
    use lightningcss::values::length::Length::*;
    match len {
        Px(v) => DeclValue::Length(Length::Px((*v).into())),
        Percent(v) => DeclValue::Length(Length::Percent((*v).into())),
        Em(v) => DeclValue::Length(Length::Em((*v).into())),
        Rem(v) => DeclValue::Length(Length::Rem((*v).into())),
        _ => DeclValue::Length(Length::Auto),
    }
}

fn convert_color(color: &lightningcss::values::color::CssColor) -> DeclValue {
    if let lightningcss::values::color::CssColor::RGBA(rgba) = color {
        DeclValue::Color(Color { r: rgba.red, g: rgba.green, b: rgba.blue, a: rgba.alpha })
    } else {
        DeclValue::Color(Color { r: 0, g: 0, b: 0, a: 255 })
    }
}
''',

    "crates/css/src/selector_trie.rs": '''//! Selector Trie

use std::collections::HashMap;

use dom::interner::InternedString;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum SelectorComponent {
    Tag(InternedString),
    Class(InternedString),
    Id(InternedString),
    Universal,
    Descendant,
    Child,
    NextSibling,
    LaterSibling,
    Attribute { name: InternedString, value: Option<InternedString>, op: AttrOp },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AttrOp {
    Exists,
    Equal,
}

#[derive(Debug, Clone)]
pub struct Selector {
    pub components: Vec<SelectorComponent>,
}

#[derive(Debug, Default)]
pub struct SelectorTrie {
    by_tag: HashMap<InternedString, Vec<RuleChain>>,
    by_class: HashMap<InternedString, Vec<RuleChain>>,
    by_id: HashMap<InternedString, Vec<RuleChain>>,
    universal: Vec<RuleChain>,
}

#[derive(Debug, Clone)]
pub struct RuleChain {
    pub rule_index: usize,
    pub remaining: Vec<SelectorComponent>,
}

impl SelectorTrie {
    pub fn new() -> Self { Self::default() }

    pub fn insert(&mut self, rule_index: usize, selector: &Selector) {
        let mut key_idx = None;
        for (i, comp) in selector.components.iter().enumerate().rev() {
            if !matches!(comp, SelectorComponent::Descendant | SelectorComponent::Child | SelectorComponent::NextSibling | SelectorComponent::LaterSibling) {
                key_idx = Some(i);
                break;
            }
        }
        let key_idx = key_idx.unwrap_or(0);
        let remaining: Vec<_> = selector.components[..key_idx].to_vec();
        let chain = RuleChain { rule_index, remaining };
        match &selector.components[key_idx] {
            SelectorComponent::Tag(tag) => { self.by_tag.entry(*tag).or_default().push(chain); }
            SelectorComponent::Class(class) => { self.by_class.entry(*class).or_default().push(chain); }
            SelectorComponent::Id(id) => { self.by_id.entry(*id).or_default().push(chain); }
            _ => { self.universal.push(chain); }
        }
    }

    pub fn lookup(&self, tag: InternedString, classes: &[InternedString], id: InternedString) -> Vec<usize> {
        let mut out = Vec::new();
        if let Some(chains) = self.by_tag.get(&tag) { out.extend(chains.iter().map(|c| c.rule_index)); }
        for class in classes { if let Some(chains) = self.by_class.get(class) { out.extend(chains.iter().map(|c| c.rule_index)); } }
        if let Some(chains) = self.by_id.get(&id) { out.extend(chains.iter().map(|c| c.rule_index)); }
        out.extend(self.universal.iter().map(|c| c.rule_index));
        out
    }

    pub fn chain_for(&self, rule_index: usize, tag: InternedString, classes: &[InternedString], id: InternedString) -> Option<&RuleChain> {
        if let Some(chains) = self.by_tag.get(&tag) { for c in chains { if c.rule_index == rule_index { return Some(c); } } }
        for class in classes { if let Some(chains) = self.by_class.get(class) { for c in chains { if c.rule_index == rule_index { return Some(c); } } } }
        if let Some(chains) = self.by_id.get(&id) { for c in chains { if c.rule_index == rule_index { return Some(c); } } }
        for c in &self.universal { if c.rule_index == rule_index { return Some(c); } }
        None
    }
}
''',

    "crates/css/src/bloom.rs": '''//! Inline Bloom Filter

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

#[derive(Debug, Clone, Copy)]
pub struct AncestorBloom {
    bits: [u64; 8],
}

impl AncestorBloom {
    pub const fn new() -> Self { Self { bits: [0; 8] } }
    pub fn clear(&mut self) { self.bits = [0; 8]; }
    pub fn insert_str(&mut self, s: &str) { self.insert(hash_str(s)); }
    pub fn insert(&mut self, hash: u64) {
        let h1 = hash as usize;
        let h2 = (hash >> 32) as usize;
        for i in 0..4 {
            let idx = (h1.wrapping_add(i * h2)) & 511;
            self.bits[idx >> 6] |= 1u64 << (idx & 63);
        }
    }
    pub fn maybe_contains_str(&self, s: &str) -> bool { self.maybe_contains(hash_str(s)) }
    pub fn maybe_contains(&self, hash: u64) -> bool {
        let h1 = hash as usize;
        let h2 = (hash >> 32) as usize;
        for i in 0..4 {
            let idx = (h1.wrapping_add(i * h2)) & 511;
            if (self.bits[idx >> 6] & (1u64 << (idx & 63))) == 0 { return false; }
        }
        true
    }
}

#[inline]
fn hash_str(s: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    s.hash(&mut hasher);
    hasher.finish()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bloom_basic() {
        let mut bloom = AncestorBloom::new();
        bloom.insert_str("nav-container");
        assert!(bloom.maybe_contains_str("nav-container"));
        assert!(!bloom.maybe_contains_str("footer"));
    }
}
''',

    "crates/css/src/computed_style.rs": '''//! Computed Style and Cache

use std::collections::HashMap;

use dom::interner::InternedString;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Display { None, Inline, Block, InlineBlock, Flex, Grid, Table, TableCell, ListItem, Contents }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Position { Static, Relative, Absolute, Fixed, Sticky }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Float { None, Left, Right }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TextAlign { Left, Right, Center, Justify, Start, End }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Visibility { Visible, Hidden, Collapse }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Length { Px(i32), Percent(i32), Em(i32), Rem(i32), Auto, Zero }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Color { pub r: u8, pub g: u8, pub b: u8, pub a: u8 }

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ComputedStyle {
    pub display: Display,
    pub position: Position,
    pub float: Float,
    pub width: Option<Length>,
    pub height: Option<Length>,
    pub margin_top: Option<Length>,
    pub margin_right: Option<Length>,
    pub margin_bottom: Option<Length>,
    pub margin_left: Option<Length>,
    pub padding_top: Option<Length>,
    pub padding_right: Option<Length>,
    pub padding_bottom: Option<Length>,
    pub padding_left: Option<Length>,
    pub color: Option<Color>,
    pub background_color: Option<Color>,
    pub font_size: Option<Length>,
    pub font_family: InternedString,
    pub text_align: TextAlign,
    pub visibility: Visibility,
    pub z_index: Option<i32>,
}

impl Default for ComputedStyle {
    fn default() -> Self {
        Self {
            display: Display::Inline, position: Position::Static, float: Float::None,
            width: None, height: None, margin_top: None, margin_right: None,
            margin_bottom: None, margin_left: None, padding_top: None,
            padding_right: None, padding_bottom: None, padding_left: None,
            color: None, background_color: None, font_size: None,
            font_family: InternedString::NONE, text_align: TextAlign::Start,
            visibility: Visibility::Visible, z_index: None,
        }
    }
}

pub struct ComputedStyleCache {
    map: HashMap<u64, u32>,
    styles: Vec<ComputedStyle>,
}

impl ComputedStyleCache {
    pub fn new() -> Self { Self { map: HashMap::new(), styles: Vec::new() } }
    pub fn get(&self, key: u64) -> Option<u32> { self.map.get(&key).copied() }
    pub fn insert(&mut self, key: u64, style: ComputedStyle) -> u32 {
        if let Some(idx) = self.map.get(&key) { return *idx; }
        let idx = self.styles.len() as u32;
        self.styles.push(style);
        self.map.insert(key, idx);
        idx
    }
    pub fn resolve(&self, index: u32) -> Option<&ComputedStyle> { self.styles.get(index as usize) }
    pub fn len(&self) -> usize { self.styles.len() }
}

impl Default for ComputedStyleCache { fn default() -> Self { Self::new() } }
''',

    "crates/css/src/matching.rs": '''//! CSS Matching Engine

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use dom::arena_dom::{FlatArenaDOM, NodeFlags, NodeId};
use dom::interner::StringInterner;

use crate::bloom::AncestorBloom;
use crate::computed_style::{ComputedStyle, ComputedStyleCache};
use crate::parser::{CssStylesheet, DeclValue, PropertyName, StyleRule};
use crate::selector_trie::{SelectorComponent, SelectorTrie};

pub struct MatchingEngine {
    trie: SelectorTrie,
    rules: Vec<StyleRule>,
    cache: ComputedStyleCache,
    use_parallel: bool,
}

impl MatchingEngine {
    pub fn new(sheet: CssStylesheet, use_parallel: bool) -> Self {
        let mut trie = SelectorTrie::new();
        for (i, rule) in sheet.rules.iter().enumerate() {
            for sel in &rule.selectors { trie.insert(i, sel); }
        }
        Self { trie, rules: sheet.rules, cache: ComputedStyleCache::new(), use_parallel }
    }

    pub fn match_document(&mut self, dom: &FlatArenaDOM, interner: &StringInterner) -> Vec<u32> {
        let elements: Vec<NodeId> = dom.descendants(NodeId::DOCUMENT)
            .filter(|n| dom.flags[n.index()].contains(NodeFlags::IS_ELEMENT))
            .collect();

        if self.use_parallel && elements.len() > 64 {
            use rayon::prelude::*;
            elements.par_iter().map(|&el| self.match_element_single(el, dom, interner)).collect()
        } else {
            elements.iter().map(|&el| self.match_element_single(el, dom, interner)).collect()
        }
    }

    fn match_element_single(&mut self, element: NodeId, dom: &FlatArenaDOM, interner: &StringInterner) -> u32 {
        let tag = dom.local_name[element.index()];
        let id = self.extract_id(element, dom, interner);
        let classes = self.extract_classes(element, dom, interner);
        let mut bloom = AncestorBloom::new();
        self.build_bloom(element, dom, interner, &mut bloom);
        let candidates = self.trie.lookup(tag, &classes, id);
        let mut matched_rules = Vec::new();
        for rule_idx in candidates {
            if let Some(chain) = self.trie.chain_for(rule_idx, tag, &classes, id) {
                if self.verify_chain(&chain.remaining, element, dom, interner, &bloom) {
                    matched_rules.push(rule_idx);
                }
            }
        }
        let cache_key = Self::compute_cache_key(&matched_rules, element, dom, interner);
        if let Some(idx) = self.cache.get(cache_key) { return idx; }
        let style = self.compute_style(&matched_rules, element, dom, interner);
        self.cache.insert(cache_key, style)
    }

    fn verify_chain(&self, remaining: &[SelectorComponent], element: NodeId, dom: &FlatArenaDOM, interner: &StringInterner, bloom: &AncestorBloom) -> bool {
        let mut current = element;
        let mut comps = remaining.iter().rev();
        while let Some(comp) = comps.next() {
            match comp {
                SelectorComponent::Descendant => {
                    let mut found = false;
                    for ancestor in dom.ancestors(current) {
                        if let Some(next_comp) = comps.next() {
                            if self.matches_component(next_comp, ancestor, dom, interner, bloom) {
                                current = ancestor;
                                found = true;
                                break;
                            }
                        }
                    }
                    if !found { return false; }
                }
                SelectorComponent::Child => {
                    if let Some(next_comp) = comps.next() {
                        let parent = dom.parent[current.index()];
                        if parent.is_none() || !self.matches_component(next_comp, parent, dom, interner, bloom) { return false; }
                        current = parent;
                    } else { return false; }
                }
                SelectorComponent::NextSibling => {
                    if let Some(next_comp) = comps.next() {
                        let prev = dom.prev_sibling[current.index()];
                        if prev.is_none() || !self.matches_component(next_comp, prev, dom, interner, bloom) { return false; }
                        current = prev;
                    } else { return false; }
                }
                SelectorComponent::LaterSibling => {
                    let mut found = false;
                    let mut sib = dom.prev_sibling[current.index()];
                    while sib.is_some() {
                        if let Some(next_comp) = comps.next() {
                            if self.matches_component(next_comp, sib, dom, interner, bloom) {
                                current = sib;
                                found = true;
                                break;
                            }
                        }
                        sib = dom.prev_sibling[sib.index()];
                    }
                    if !found { return false; }
                }
                _ => { if !self.matches_component(comp, current, dom, interner, bloom) { return false; } }
            }
        }
        true
    }

    fn matches_component(&self, comp: &SelectorComponent, node: NodeId, dom: &FlatArenaDOM, interner: &StringInterner, _bloom: &AncestorBloom) -> bool {
        match comp {
            SelectorComponent::Tag(tag) => dom.local_name[node.index()] == *tag,
            SelectorComponent::Class(class) => {
                let attrs = dom.get_attributes(node);
                for attr in attrs {
                    if interner.resolve(attr.name) == Some("class") {
                        if let Some(val) = interner.resolve(attr.value) {
                            for c in val.split_whitespace() { if interner.intern(c) == *class { return true; } }
                        }
                    }
                }
                false
            }
            SelectorComponent::Id(id) => {
                let attrs = dom.get_attributes(node);
                for attr in attrs { if interner.resolve(attr.name) == Some("id") && attr.value == *id { return true; } }
                false
            }
            SelectorComponent::Universal => true,
            SelectorComponent::Attribute { name, value, op } => {
                let attrs = dom.get_attributes(node);
                for attr in attrs {
                    if attr.name == *name {
                        match op {
                            crate::selector_trie::AttrOp::Exists => return true,
                            crate::selector_trie::AttrOp::Equal => { if let Some(v) = value { if attr.value == *v { return true; } } }
                        }
                    }
                }
                false
            }
            SelectorComponent::Descendant | SelectorComponent::Child | SelectorComponent::NextSibling | SelectorComponent::LaterSibling => true,
        }
    }

    fn build_bloom(&self, node: NodeId, dom: &FlatArenaDOM, interner: &StringInterner, bloom: &mut AncestorBloom) {
        for ancestor in dom.ancestors(node) {
            if let Some(name) = interner.resolve(dom.local_name[ancestor.index()]) { bloom.insert_str(name); }
            let attrs = dom.get_attributes(ancestor);
            for attr in attrs {
                if interner.resolve(attr.name) == Some("class") {
                    if let Some(val) = interner.resolve(attr.value) { for class in val.split_whitespace() { bloom.insert_str(class); } }
                }
                if interner.resolve(attr.name) == Some("id") {
                    if let Some(val) = interner.resolve(attr.value) { bloom.insert_str(val); }
                }
            }
        }
    }

    fn extract_classes(&self, node: NodeId, dom: &FlatArenaDOM, interner: &StringInterner) -> Vec<InternedString> {
        let mut out = Vec::new();
        let attrs = dom.get_attributes(node);
        for attr in attrs {
            if interner.resolve(attr.name) == Some("class") {
                if let Some(val) = interner.resolve(attr.value) { for c in val.split_whitespace() { out.push(interner.intern(c)); } }
            }
        }
        out
    }

    fn extract_id(&self, node: NodeId, dom: &FlatArenaDOM, interner: &StringInterner) -> InternedString {
        let attrs = dom.get_attributes(node);
        for attr in attrs { if interner.resolve(attr.name) == Some("id") { return attr.value; } }
        InternedString::NONE
    }

    fn compute_cache_key(matched: &[usize], element: NodeId, dom: &FlatArenaDOM, interner: &StringInterner) -> u64 {
        let mut hasher = DefaultHasher::new();
        matched.hash(&mut hasher);
        let attrs = dom.get_attributes(element);
        for attr in attrs {
            if interner.resolve(attr.name) == Some("style") {
                if let Some(val) = interner.resolve(attr.value) { val.hash(&mut hasher); }
            }
        }
        hasher.finish()
    }

    fn compute_style(&self, matched: &[usize], _element: NodeId, _dom: &FlatArenaDOM, _interner: &StringInterner) -> ComputedStyle {
        let mut style = ComputedStyle::default();
        for &rule_idx in matched {
            let rule = &self.rules[rule_idx];
            for decl in &rule.declarations {
                match (&decl.property, &decl.value) {
                    (PropertyName::Display, DeclValue::Display(v)) => style.display = *v,
                    (PropertyName::Position, DeclValue::Position(v)) => style.position = *v,
                    (PropertyName::Float, DeclValue::Float(v)) => style.float = *v,
                    (PropertyName::Width, DeclValue::Length(v)) => style.width = Some(*v),
                    (PropertyName::Height, DeclValue::Length(v)) => style.height = Some(*v),
                    (PropertyName::MarginTop, DeclValue::Length(v)) => style.margin_top = Some(*v),
                    (PropertyName::MarginRight, DeclValue::Length(v)) => style.margin_right = Some(*v),
                    (PropertyName::MarginBottom, DeclValue::Length(v)) => style.margin_bottom = Some(*v),
                    (PropertyName::MarginLeft, DeclValue::Length(v)) => style.margin_left = Some(*v),
                    (PropertyName::PaddingTop, DeclValue::Length(v)) => style.padding_top = Some(*v),
                    (PropertyName::PaddingRight, DeclValue::Length(v)) => style.padding_right = Some(*v),
                    (PropertyName::PaddingBottom, DeclValue::Length(v)) => style.padding_bottom = Some(*v),
                    (PropertyName::PaddingLeft, DeclValue::Length(v)) => style.padding_left = Some(*v),
                    (PropertyName::Color, DeclValue::Color(v)) => style.color = Some(*v),
                    (PropertyName::BackgroundColor, DeclValue::Color(v)) => style.background_color = Some(*v),
                    (PropertyName::FontSize, DeclValue::Length(v)) => style.font_size = Some(*v),
                    (PropertyName::FontFamily, DeclValue::String(v)) => style.font_family = *v,
                    (PropertyName::TextAlign, DeclValue::TextAlign(v)) => style.text_align = *v,
                    (PropertyName::Visibility, DeclValue::Visibility(v)) => style.visibility = *v,
                    (PropertyName::ZIndex, DeclValue::ZIndex(v)) => style.z_index = Some(*v),
                    _ => {}
                }
            }
        }
        style
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn match_simple_selector() {
        let mut interner = StringInterner::new();
        let css = "div { display: block; }";
        let sheet = CssStylesheet::parse(css, &mut interner).unwrap();
        let engine = MatchingEngine::new(sheet, false);
        let mut dom = dom::arena_dom::FlatArenaDOM::new();
        let div = dom.create_element_node(
            interner.intern("div"),
            interner.intern("http://www.w3.org/1999/xhtml"),
            &[],
            dom::arena_dom::NodeFlags::IS_ELEMENT,
        );
        dom.append_child(dom::arena_dom::NodeId::DOCUMENT, div);
        let styles = engine.match_document(&dom, &interner);
        assert_eq!(styles.len(), 1);
        let computed = engine.cache.resolve(styles[0]).unwrap();
        assert_eq!(computed.display, crate::computed_style::Display::Block);
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 7: Layout
    # -------------------------------------------------------------------------
    "crates/layout/Cargo.toml": '''[package]
name = "layout"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
dom = { path = "../dom" }
memory = { path = "../memory" }
platform = { path = "../platform" }
css = { path = "../css" }
taffy = "0.4"
''',

    "crates/layout/src/lib.rs": '''//! # Layout Engine
//!
//! Integrates Taffy for modern layout (Flexbox, CSS Grid) and provides a
//! Servo-inspired block/inline flow engine for traditional document layout.

pub mod block;
pub mod inline;
pub mod tree;

pub use tree::{LayoutNode, LayoutNodeId, LayoutTree};
''',

    "crates/layout/src/tree.rs": '''//! Layout Tree

use std::cell::Cell;

use dom::arena_dom::{FlatArenaDOM, NodeFlags, NodeId};
use memory::arena::ArenaAllocator;

use taffy::{NodeId as TaffyNodeId, Taffy, Style};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LayoutNodeId(u32);

impl LayoutNodeId {
    pub const NONE: Self = Self(u32::MAX);
    pub const fn new(index: u32) -> Self { Self(index) }
    pub const fn index(self) -> usize { self.0 as usize }
    pub const fn is_none(self) -> bool { self.0 == u32::MAX }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LayoutType {
    Taffy,
    Block,
    Inline,
    Text,
    Replaced,
    None,
}

#[derive(Debug, Clone)]
pub struct LayoutNode {
    pub dom_node: NodeId,
    pub layout_type: LayoutType,
    pub taffy_node: Option<TaffyNodeId>,
    pub rel_x: f32,
    pub rel_y: f32,
    pub width: f32,
    pub height: f32,
    pub abs_x: f32,
    pub abs_y: f32,
    pub is_dirty: Cell<bool>,
    pub style_index: u32,
}

pub struct LayoutTree {
    nodes: Vec<LayoutNode>,
    dom_to_layout: Vec<LayoutNodeId>,
    taffy: Taffy,
    pub layout_arena: ArenaAllocator,
    root: LayoutNodeId,
}

impl LayoutTree {
    pub fn new(dom: &FlatArenaDOM, arena_capacity: usize) -> Option<Self> {
        let arena = ArenaAllocator::new(arena_capacity)?;
        let mut tree = Self {
            nodes: Vec::with_capacity(dom.len()),
            dom_to_layout: vec![LayoutNodeId::NONE; dom.len()],
            taffy: Taffy::new(),
            layout_arena: arena,
            root: LayoutNodeId::NONE,
        };
        tree.build_from_dom(dom);
        Some(tree)
    }

    fn build_from_dom(&mut self, dom: &FlatArenaDOM) {
        self.nodes.clear();
        self.dom_to_layout.fill(LayoutNodeId::NONE);
        let root = self.create_node(dom, NodeId::DOCUMENT, LayoutType::Block);
        self.root = root;
        self.build_children(dom, NodeId::DOCUMENT, root);
    }

    fn build_children(&mut self, dom: &FlatArenaDOM, dom_parent: NodeId, layout_parent: LayoutNodeId) {
        let mut child = dom.first_child[dom_parent.index()];
        while child.is_some() {
            let flags = dom.flags[child.index()];
            let ltype = if flags.contains(NodeFlags::IS_TEXT) {
                LayoutType::Text
            } else if flags.contains(NodeFlags::IS_ELEMENT) {
                LayoutType::Block
            } else {
                LayoutType::None
            };
            let _lnode = self.create_node(dom, child, ltype);
            child = dom.next_sibling[child.index()];
        }
    }

    fn create_node(&mut self, dom: &FlatArenaDOM, dom_node: NodeId, ltype: LayoutType) -> LayoutNodeId {
        let id = LayoutNodeId::new(self.nodes.len() as u32);
        let taffy_node = if ltype == LayoutType::Taffy {
            self.taffy.new_leaf(Style::default()).ok()
        } else { None };

        self.nodes.push(LayoutNode {
            dom_node,
            layout_type: ltype,
            taffy_node,
            rel_x: 0.0, rel_y: 0.0,
            width: 0.0, height: 0.0,
            abs_x: 0.0, abs_y: 0.0,
            is_dirty: Cell::new(true),
            style_index: dom.style_index[dom_node.index()],
        });

        if dom_node.index() < self.dom_to_layout.len() {
            self.dom_to_layout[dom_node.index()] = id;
        } else {
            self.dom_to_layout.resize(dom_node.index() + 1, LayoutNodeId::NONE);
            self.dom_to_layout[dom_node.index()] = id;
        }
        id
    }

    pub fn mark_dirty(&self, dom: &FlatArenaDOM, node: NodeId) {
        if let Some(lid) = self.dom_to_layout.get(node.index()) {
            if let Some(lid) = lid.as_some() {
                self.mark_layout_dirty_recursive(lid);
            }
        }
        let mut child = dom.first_child[node.index()];
        while child.is_some() {
            self.mark_dirty(dom, child);
            child = dom.next_sibling[child.index()];
        }
    }

    fn mark_layout_dirty_recursive(&self, node: LayoutNodeId) {
        self.nodes[node.index()].is_dirty.set(true);
    }

    pub fn compute_layout(&mut self, dom: &FlatArenaDOM, viewport_width: f32, viewport_height: f32) {
        self.layout_arena.reset();
        if let Some(root_taffy) = self.nodes[self.root.index()].taffy_node {
            let _ = self.taffy.compute_layout(
                root_taffy,
                taffy::Size {
                    width: taffy::AvailableSpace::Definite(viewport_width),
                    height: taffy::AvailableSpace::Definite(viewport_height),
                },
            );
        }
        self.compute_block_flow(dom, self.root, 0.0, 0.0, viewport_width);
        for node in &mut self.nodes { node.is_dirty.set(false); }
    }

    fn compute_block_flow(&mut self, dom: &FlatArenaDOM, layout_node: LayoutNodeId, abs_x: f32, abs_y: f32, container_width: f32) {
        let node = &self.nodes[layout_node.index()];
        let dom_node = node.dom_node;
        let mut cursor_y = abs_y;
        let mut child_dom = dom.first_child[dom_node.index()];

        while child_dom.is_some() {
            if let Some(&lid) = self.dom_to_layout.get(child_dom.index()) {
                if lid.is_none() {
                    child_dom = dom.next_sibling[child_dom.index()];
                    continue;
                }
                let child_height = if dom.flags[child_dom.index()].contains(NodeFlags::IS_TEXT) { 16.0 } else { 20.0 };
                self.nodes[lid.index()].abs_x = abs_x;
                self.nodes[lid.index()].abs_y = cursor_y;
                self.nodes[lid.index()].width = container_width;
                self.nodes[lid.index()].height = child_height;
                cursor_y += child_height;
                if dom.flags[child_dom.index()].contains(NodeFlags::IS_ELEMENT) {
                    self.compute_block_flow(dom, lid, abs_x, cursor_y - child_height, container_width);
                }
            }
            child_dom = dom.next_sibling[child_dom.index()];
        }
        if layout_node != self.root {
            self.nodes[layout_node.index()].height = cursor_y - abs_y;
        }
    }

    pub fn get_layout(&self, dom_node: NodeId) -> Option<&LayoutNode> {
        self.dom_to_layout.get(dom_node.index()).and_then(|&id| {
            if id.is_none() { None } else { self.nodes.get(id.index()) }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dom::arena_dom::{FlatArenaDOM, NodeFlags};
    use dom::interner::StringInterner;

    #[test]
    fn layout_tree_creation() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        let div = dom.create_element_node(
            interner.intern("div"),
            interner.intern("http://www.w3.org/1999/xhtml"),
            &[],
            NodeFlags::IS_ELEMENT,
        );
        dom.append_child(NodeId::DOCUMENT, div);
        let tree = LayoutTree::new(&dom, 1024 * 1024).expect("layout tree");
        assert!(!tree.root.is_none());
        assert_eq!(tree.nodes.len(), 2);
    }
}
''',

    "crates/layout/src/block.rs": '''//! Servo-Inspired Block Layout

use dom::arena_dom::{FlatArenaDOM, NodeFlags, NodeId};

use crate::tree::{LayoutNodeId, LayoutTree};

pub struct BlockLayoutContext<'a> {
    pub tree: &'a mut LayoutTree,
    pub dom: &'a FlatArenaDOM,
    pub container_width: f32,
    pub container_height: f32,
}

impl<'a> BlockLayoutContext<'a> {
    pub fn layout_block_children(&mut self, block_node: LayoutNodeId, start_y: f32) -> f32 {
        let dom_node = self.tree.nodes[block_node.index()].dom_node;
        let mut cursor_y = start_y;
        let mut child_dom = self.dom.first_child[dom_node.index()];
        while child_dom.is_some() {
            if let Some(&lid) = self.tree.dom_to_layout.get(child_dom.index()) {
                if lid.is_none() {
                    child_dom = self.dom.next_sibling[child_dom.index()];
                    continue;
                }
                let child_node = &self.tree.nodes[lid.index()];
                let is_block = child_node.layout_type == crate::tree::LayoutType::Block
                    || child_node.layout_type == crate::tree::LayoutType::Taffy;
                if is_block {
                    self.tree.nodes[lid.index()].abs_x = 0.0;
                    self.tree.nodes[lid.index()].abs_y = cursor_y;
                    self.tree.nodes[lid.index()].width = self.container_width;
                    let child_height = self.layout_block_children(lid, cursor_y);
                    self.tree.nodes[lid.index()].height = child_height;
                    cursor_y += child_height;
                }
            }
            child_dom = self.dom.next_sibling[child_dom.index()];
        }
        cursor_y - start_y
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dom::arena_dom::{FlatArenaDOM, NodeFlags};
    use dom::interner::StringInterner;

    #[test]
    fn block_stack_height() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        let a = dom.create_element_node(interner.intern("div"), interner.intern("http://www.w3.org/1999/xhtml"), &[], NodeFlags::IS_ELEMENT);
        let b = dom.create_element_node(interner.intern("div"), interner.intern("http://www.w3.org/1999/xhtml"), &[], NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, a);
        dom.append_child(NodeId::DOCUMENT, b);
        let mut tree = LayoutTree::new(&dom, 1024 * 1024).unwrap();
        let mut ctx = BlockLayoutContext {
            tree: &mut tree,
            dom: &dom,
            container_width: 800.0,
            container_height: 600.0,
        };
        let height = ctx.layout_block_children(ctx.tree.root, 0.0);
        assert!(height > 0.0);
    }
}
''',

    "crates/layout/src/inline.rs": '''//! Inline Layout

use dom::arena_dom::{FlatArenaDOM, NodeFlags, NodeId};

use crate::tree::{LayoutNodeId, LayoutTree};

#[derive(Debug, Clone, Copy)]
pub struct InlineFragment {
    pub dom_node: NodeId,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

pub fn layout_inline_line(
    tree: &mut LayoutTree,
    dom: &FlatArenaDOM,
    block_layout_node: LayoutNodeId,
    start_x: f32,
    start_y: f32,
    max_width: f32,
) -> (f32, Vec<InlineFragment>) {
    let dom_node = tree.nodes[block_layout_node.index()].dom_node;
    let mut cursor_x = start_x;
    let mut fragments = Vec::new();
    let mut child_dom = dom.first_child[dom_node.index()];
    while child_dom.is_some() {
        if let Some(&lid) = tree.dom_to_layout.get(child_dom.index()) {
            if lid.is_none() {
                child_dom = dom.next_sibling[child_dom.index()];
                continue;
            }
            let width = if dom.flags[child_dom.index()].contains(NodeFlags::IS_TEXT) { 80.0 } else { 100.0 };
            if cursor_x + width > start_x + max_width { break; }
            fragments.push(InlineFragment {
                dom_node: child_dom,
                x: cursor_x,
                y: start_y,
                width,
                height: 16.0,
            });
            cursor_x += width;
        }
        child_dom = dom.next_sibling[child_dom.index()];
    }
    (cursor_x - start_x, fragments)
}

#[cfg(test)]
mod tests {
    use super::*;
    use dom::arena_dom::{FlatArenaDOM, NodeFlags};
    use dom::interner::StringInterner;

    #[test]
    fn inline_line_basic() {
        let mut dom = FlatArenaDOM::new();
        let mut interner = StringInterner::new();
        let span = dom.create_element_node(interner.intern("span"), interner.intern("http://www.w3.org/1999/xhtml"), &[], NodeFlags::IS_ELEMENT);
        dom.append_child(NodeId::DOCUMENT, span);
        let mut tree = LayoutTree::new(&dom, 1024 * 1024).unwrap();
        let (width, fragments) = layout_inline_line(&mut tree, &dom, tree.root, 0.0, 0.0, 800.0);
        assert!(width >= 0.0);
        assert!(!fragments.is_empty());
    }
}
''',

    # -------------------------------------------------------------------------
    # Module 8: Renderer
    # -------------------------------------------------------------------------
    "crates/renderer/Cargo.toml": '''[package]
name = "renderer"
version.workspace = true
edition.workspace = true
rust-version.workspace = true

[dependencies]
dom = { path = "../dom" }
memory = { path = "../memory" }
platform = { path = "../platform" }
layout = { path = "../layout" }
css = { path = "../css" }
wgpu = "0.20"
raw-window-handle = "0.6"
''',

    "crates/renderer/src/lib.rs": '''//! # Renderer Subsystem
//!
//! MVP Phase 1: Sequential Display List rendered via wgpu.
//! Phase 2 architecture: Render Graph, Tile Cache, Glyph Atlas, Partial
//! Repaint, and GPU Compositing are prepared as structural extensions.

pub mod display_list;
pub mod pipeline;
pub mod wgpu_ctx;

pub use display_list::{DisplayList, DisplayListBuilder, DrawCommand};
pub use pipeline::RenderPipeline;
pub use wgpu_ctx::WgpuContext;
''',

    "crates/renderer/src/wgpu_ctx.rs": '''//! Wgpu Context

use wgpu::{Adapter, Device, Instance, Queue, Surface, SurfaceConfiguration};

pub struct WgpuContext {
    pub instance: Instance,
    pub adapter: Adapter,
    pub device: Device,
    pub queue: Queue,
    pub surface: Option<Surface<'static>>,
    pub config: Option<SurfaceConfiguration>,
}

impl WgpuContext {
    pub async fn new_headless() -> Option<Self> {
        let instance = Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::PRIMARY,
            ..Default::default()
        });
        let adapter = instance
            .request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::HighPerformance,
                compatible_surface: None,
                force_fallback_adapter: false,
            })
            .await?;
        let (device, queue) = adapter
            .request_device(
                &wgpu::DeviceDescriptor {
                    label: Some("m-engine-device"),
                    required_features: wgpu::Features::empty(),
                    required_limits: wgpu::Limits::default(),
                    memory_hints: wgpu::MemoryHints::Performance,
                },
                None,
            )
            .await
            .ok()?;
        Some(Self { instance, adapter, device, queue, surface: None, config: None })
    }

    pub fn configure_surface(&mut self, surface: Surface<'static>, width: u32, height: u32) {
        let caps = surface.get_capabilities(&self.adapter);
        let format = caps.formats.iter().find(|f| f.is_srgb()).copied().unwrap_or(caps.formats[0]);
        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format,
            width,
            height,
            present_mode: wgpu::PresentMode::AutoVsync,
            desired_maximum_frame_latency: 2,
            alpha_mode: caps.alpha_modes[0],
            view_formats: vec![],
        };
        surface.configure(&self.device, &config);
        self.config = Some(config);
        self.surface = Some(surface);
    }

    pub fn begin_frame(&self) -> Option<(wgpu::SurfaceTexture, wgpu::TextureView)> {
        let surface = self.surface.as_ref()?;
        let output = surface.get_current_texture().ok()?;
        let view = output.texture.create_view(&wgpu::TextureViewDescriptor::default());
        Some((output, view))
    }

    pub fn submit(&self, encoder: wgpu::CommandEncoder) {
        self.queue.submit(std::iter::once(encoder.finish()));
    }
}
''',

    "crates/renderer/src/display_list.rs": '''//! Display List

use css::computed_style::Color;

#[derive(Debug, Clone, Copy)]
pub enum DrawCommand {
    Rect { x: f32, y: f32, width: f32, height: f32, color: Color },
    Border { x: f32, y: f32, width: f32, height: f32, color: Color, width_px: f32 },
    TextRun { x: f32, y: f32, glyph_start: u32, glyph_count: u32, color: Color },
    Image { x: f32, y: f32, width: f32, height: f32, texture_id: u32 },
    Clip { x: f32, y: f32, width: f32, height: f32 },
    ClipPop,
}

#[derive(Debug, Clone, Default)]
pub struct DisplayList {
    pub commands: Vec<DrawCommand>,
}

impl DisplayList {
    pub fn new() -> Self { Self::default() }
    pub fn clear(&mut self) { self.commands.clear(); }
    pub fn push(&mut self, cmd: DrawCommand) { self.commands.push(cmd); }
    pub fn is_empty(&self) -> bool { self.commands.is_empty() }
    pub fn len(&self) -> usize { self.commands.len() }
}

pub struct DisplayListBuilder<'a> {
    pub list: DisplayList,
    pub ctx: &'a crate::wgpu_ctx::WgpuContext,
}

impl<'a> DisplayListBuilder<'a> {
    pub fn new(ctx: &'a crate::wgpu_ctx::WgpuContext) -> Self {
        Self { list: DisplayList::new(), ctx }
    }

    pub fn build(&mut self, layout_tree: &layout::tree::LayoutTree) {
        self.list.clear();
        for node in &layout_tree.nodes {
            if node.width > 0.0 && node.height > 0.0 {
                self.list.push(DrawCommand::Rect {
                    x: node.abs_x, y: node.abs_y,
                    width: node.width, height: node.height,
                    color: Color { r: 240, g: 240, b: 240, a: 255 },
                });
            }
        }
    }

    pub fn finish(self) -> DisplayList { self.list }
}
''',

    "crates/renderer/src/pipeline.rs": '''//! Render Pipeline

use wgpu::{RenderPass, RenderPipeline as WgpuPipeline};

pub struct RenderPipeline {
    pub solid_pipeline: WgpuPipeline,
    pub bind_group_layout: wgpu::BindGroupLayout,
}

impl RenderPipeline {
    pub fn new(device: &wgpu::Device, target_format: wgpu::TextureFormat) -> Self {
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("solid-shader"),
            source: wgpu::ShaderSource::Wgsl(std::borrow::Cow::Borrowed(include_str!("solid.wgsl"))),
        });
        let bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("bind-group-layout"),
            entries: &[],
        });
        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pipeline-layout"),
            bind_group_layouts: &[&bind_group_layout],
            push_constant_ranges: &[],
        });
        let solid_pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("solid-pipeline"),
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: "vs_main",
                buffers: &[wgpu::VertexBufferLayout {
                    array_stride: 8 * 4,
                    step_mode: wgpu::VertexStepMode::Vertex,
                    attributes: &wgpu::vertex_attr_array![0 => Float32x2, 1 => Float32x4],
                }],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: "fs_main",
                targets: &[Some(wgpu::ColorTargetState {
                    format: target_format,
                    blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::TriangleList,
                ..Default::default()
            },
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
        });
        Self { solid_pipeline, bind_group_layout }
    }

    pub fn render_display_list<'a>(&'a self, pass: &mut RenderPass<'a>, _display_list: &'a crate::display_list::DisplayList) {
        pass.set_pipeline(&self.solid_pipeline);
    }
}
''',

    "crates/renderer/src/solid.wgsl": '''// Vertex shader
struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) color: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) color: vec4<f32>,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.clip_position = vec4<f32>(in.position, 0.0, 1.0);
    out.color = in.color;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return in.color;
}
''',
}

# =============================================================================
# SCRIPT LOGIC
# =============================================================================

def create_project():
    print("[m-engine] Reconstructing workspace...")
    for path, content in FILES.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  written: {path}")

    print("[m-engine] Packing m-engine.zip...")
    with zipfile.ZipFile("m-engine.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for path in FILES:
            zf.write(path)
    print("[m-engine] Done. Archive: m-engine.zip")

if __name__ == "__main__":
    create_project()
