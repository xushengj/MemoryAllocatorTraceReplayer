# MemoryAllocatorTraceReplayer

This repo contains my debugging tools for a custom allocator used in my research. If you have a custom allocator written in C that is found to be buggy (e.g. programs crash when that allocator is used) and you have at least one trace of calls to allocator functions, this repo contains the template that you may utilize to generate a checking program that performs exactly the same sequence of allocator function calls and examine whether there are data corruptions caused by the allocator.

`checker.c` contains helper functions to register and validate allocated memory regions. It also implements `main()`, which just calls `trace_main()` in a generated file `trace.inc`.
`codegen.py` contains a trace log parser that reads a trace and produce `trace.inc`, which is a C source file fragment that contains a function performing all the allocation and validation calls

The expected workflow is:

1. modify the `codegen.py` script to adapt:
   * the format of your trace file. `codegen.py` expects each line in the trace to be matched against a given regular expression, and fields are extracted from there.
   * how your allocator should be called
   * (if your allocator has functions that verify its internal states) add calls to your own internal state validation functions
2. run `codegen.py` on your trace to generate `trace.inc`
3. compile and link `checker.c` with your allocator source.

## Why a trace replayer like this?

When debugging an allocator, you will find that the returned pointer address may not be the same for each run. If you don't know the crashing program perfectly well and / or having trouble shrinking down the code needed to reproduce the allocator call sequence exactly, you will find replaying the log to be non-trivial. Plus, debugging the allocator means that you will try to avoid as much dynamic memory allocation as possible, which makes the problem even harder.

To solve the non-deterministic pointer address issue, `codegen.py` interprets each address in the log to be a "name" of memory location instead of a concrete address. Whenever a new address is returned from `malloc()` equivalent functions at runtime, it is assigned a name derived from the original address in the trace. When the name is referenced in the original trace (e.g. in a subsequent `free()`), the new address is then used as the concrete value contained by the name. In implementation each name is associated with an index and all pointers are stored in a global variable array. All name translations are performed statically.

## I don't understand something in `codegen.py`

My allocator contains following functions that will be called from generated `trace.inc`:

* `ifp_test_malloc()`, which is like `malloc()` but takes an additional pointer parameter for our internal use.
* `ifp_test_free()` is functionally identical to `free()`
* `checkRoot()` is the internal state validation function in my allocator.

My research involves utilizing unused high 16 bits in a modified 64 bits architecture, and `CLEAN_PTR()` macro erases them so that the test program can run on any 64 bits environment (mainly x86-64), not just our modified architecture.

Other functions being called from generated `trace.inc` are either from libc or in `checker.c`.
