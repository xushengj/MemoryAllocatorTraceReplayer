#include <stdlib.h>

void* ifp_test_malloc(void** root, size_t size)
{
  (void) root;
  return malloc(size);
}

void ifp_test_free(void* slot)
{
  free(slot);
}
