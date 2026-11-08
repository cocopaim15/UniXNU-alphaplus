/*
 * Freestanding progress marks for the alphaplus kernel.
 *
 * Injected into a code cave and called from the bring-up call sites: paints one
 * red square on the bottom of the frame buffer per stage reached, so the screen
 * itself shows how far the kernel got - no serial console, no RAM survival.
 *
 * PE_state layout (from PE_init_platform): +0x08 v_baseAddr, +0x10 v_rowBytes,
 * +0x18 v_width, +0x20 v_height, +0x28 v_depth. ml_io_map() returns a kernel
 * mapping of a physical range and is available once arm_vm_init() has run.
 */
typedef unsigned long long u64;
typedef unsigned int       u32;

extern void *ml_io_map (u64 pa, u64 size);

#define PE_STATE ((volatile u64 *)0xfffffff007204150ULL)

void
alpha_mark (int n)
{
	u64  pa;
	u64  rb;
	u64  h;
	u64  bytes;
	u64  span;
	u64  x;
	u64  y;
	u64  row;
	u64  col;
	u32  *fb;

	pa = PE_STATE[1];
	rb = PE_STATE[2];
	h  = PE_STATE[4];
	if ((pa == 0) || (rb == 0) || (h == 0)) {
		return;
	}
	x = 16 + (u64)(n - 1) * 70;
	y = (h > 240) ? (h - 200) : 0;

	/*
	 * Map only the 64 rows that carry the square: a whole-screen mapping is
	 * ~18 MB of page tables and ml_io_map() refuses it this early.
	 */
	span = rb * 64;
	bytes = span;
	fb = (u32 *)ml_io_map (pa + y * rb, span);
	if (fb == 0) {
		return;
	}

	for (row = 0; row < 64; row++) {
		u32 *line = fb + (y + row) * (rb / 4) + x;
		for (col = 0; col < 64; col++) {
			line[col] = 0xFFFF0000U;
		}
	}
}
