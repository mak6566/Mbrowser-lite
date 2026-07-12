# Mbrowser Lite

Mbrowser Lite is an extremely fast and memory-efficient web browser powered by the specialized m-engine V1 core. Its primary goal is to deliver top-tier performance, high responsiveness, and stability under strict hardware resource constraints.

## System Requirements & Key Performance Indicators (KPI)
* **Hardware Minimum:** Smooth execution requires a device with at least 500 MB of RAM.
* **Cold Start Footprint:** Optimized to utilize a mere 25 MB of RAM upon initial startup.
* **Standard Web Browsing:** Average memory consumption remains under 50 MB of RAM when rendering standard web content.
* **Target Platforms:** Embedded architectures, older mobile chipsets, and restricted environments such as Termux.

## Architecture & Core Tech Stack
The browser core is written entirely in Rust, providing native memory safety without the runtime overhead of a Garbage Collector, significantly cutting down on resource usage.

* **JavaScript Runtime:** Implements a lightweight QuickJS instance (JIT-less) to maintain an exceptionally low memory baseline (~1 MB RAM), utilizing direct native Rust bindings for DOM manipulation and Web APIs.
* **Graphics Pipeline:** Features hardware-accelerated rendering via `wgpu` with an advanced Render Graph and Tile Caching system targeting Vulkan, Metal, and DirectX 12 natively.
* **CSS & Layout Engines:** Integrates `lightningcss` for high-throughput style tokenization alongside the `Taffy` layout engine for high-speed Flexbox and CSS Grid computations.
* **Text Processing Subsystem:** Powered by `cosmic-text` to achieve full text shaping and robust font fallback functionality directly coupled with the GPU pipeline.
* **Data Layer (DOM):** Avoids pointer-heavy OOP overhead by implementing a Compact Flat Arena DOM built on the Structure of Arrays (SoA) paradigm, replacing 64-bit pointers with 32-bit indices.

## Low-Level Optimizations
* **Capability Profiles:** The system automatically detects host specifications at startup and applies one of four performance configurations (ranging from Embedded to High) to scale caching and internal concurrency behaviors dynamically.
* **Tiered Allocator System:** Bypasses standard system allocators entirely for critical page structures. It maps data to three distinct strategies (Slab Allocator, Arena Allocator, and Direct OS mmap) to target zero `malloc` and `free` overhead within the main rendering loop.
* **Multi-Level CSS Matching:** Employs a right-to-left Selector Trie coupled with highly compact inline Bloom filters to achieve O(1) parent class verification, pruning unmatched rules instantaneously.
* **Asynchronous Inline Media Downscaling:** Streamed decoders for WebP, PNG, and JPEG formats process rows sequentially using SIMD instructions to resize assets down to their final layout boundaries during parsing, lowering uncompressed graphic allocation from dozens of megabytes down to hundreds of kilobytes.

## Project Philosophy
Mbrowser Lite is not designed to compete with heavy modern rendering engines in raw computing power on top-end multicore hardware; its purpose is to establish maximum memory and energy efficiency. The result is an uncompromisingly fast browser engineered explicitly for resource-constrained deployment environments.
