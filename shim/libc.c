/*
 * The few libc functions a freestanding link can still need.
 *
 * clang emits real calls to these where gcc folded them away, so the shim has
 * to carry them: `__builtin_strcmp` on a freestanding target is a call to
 * strcmp, and the compiler may also synthesise memcpy/memset from structure
 * assignments and array initialisation.
 *
 * None of these are optimised. They run with the MMU and caches off, so they
 * touch memory through normal loads and stores and nothing more.
 */
#include <stddef.h>
#include <stdint.h>

void *memcpy(void *dst, const void *src, size_t n)
{
	volatile uint8_t *d = (volatile uint8_t *)dst;
	volatile const uint8_t *s = (volatile const uint8_t *)src;
	for (size_t i = 0; i < n; i++)
		d[i] = s[i];
	return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
	volatile uint8_t *d = (volatile uint8_t *)dst;
	volatile const uint8_t *s = (volatile const uint8_t *)src;
	if (d < s)
		for (size_t i = 0; i < n; i++)
			d[i] = s[i];
	else
		for (size_t i = n; i > 0; i--)
			d[i - 1] = s[i - 1];
	return dst;
}

void *memset(void *dst, int c, size_t n)
{
	volatile uint8_t *d = (volatile uint8_t *)dst;
	for (size_t i = 0; i < n; i++)
		d[i] = (uint8_t)c;
	return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
	const uint8_t *x = (const uint8_t *)a, *y = (const uint8_t *)b;
	for (size_t i = 0; i < n; i++)
		if (x[i] != y[i])
			return x[i] - y[i];
	return 0;
}

int strcmp(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return (unsigned char)*a - (unsigned char)*b;
}

size_t strlen(const char *s)
{
	size_t n = 0;
	while (s[n])
		n++;
	return n;
}
