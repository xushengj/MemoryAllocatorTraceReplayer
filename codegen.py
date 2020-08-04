#!/usr/bin/env python

import re
import os
import sys

class PtrRenamer:
  def __init__(self):
    self.renameMap = dict() # ptr addr / name -> index
    self.activeMap = dict() # index -> ptr addr / name
    self.numPtrs = 0 # max number of pointers
    self.ptrSlotFreeList = [] # ptr indices less than numPtrs that are currently not used
  
  def isNameUsed(self, name):
    return (name in self.renameMap)
  
  def getIndex(self, name):
    assert name in self.renameMap
    return self.renameMap[name]
  
  def release(self, name):
    assert name in self.renameMap
    index = self.renameMap[name]
    self.activeMap.pop(index)
    self.renameMap.pop(name)
    self.ptrSlotFreeList.append(index)
  
  def allocate(self, name):
    assert name not in self.renameMap
    index = self.numPtrs
    if len(self.ptrSlotFreeList) > 0:
      index = self.ptrSlotFreeList.pop()
    else:
      self.numPtrs += 1
    
    self.renameMap[name] = index
    self.activeMap[index] = name
    return index
  
  def forceAllocate_NoRecycling(self):
    index = self.numPtrs
    self.numPtrs += 1
    return index

def generatePtrName(linecount):
  return 'ptr_{}'.format(str(linecount))

def processTrace(traceName, outputFileName):
  with open(traceName, 'r') as f:
    line = f.readline()
    lc = 1
    name_null = '(nil)'
    renamer = PtrRenamer()
    regex = re.compile(r'(?P<idx>\d) \(\w+\): \(ptr=(?P<ptr>[\w\d\(\)]+), root=(?:[\w\d\(\)]+), md=(?:[\w\d\(\)]+), size=(?P<size>\d+), num=(?P<num>\d+)\) -> (?P<retptr>[\w\d\(\)]+)')
    code_frag = """#include <string.h>
#define CLEAN_PTR(ptr) (void*)((((uintptr_t)ptr) << 16) >> 16)
void* ifp_test_malloc(void** root, size_t size);
void  ifp_test_free(void* slot);

#ifndef CHECK_OPS
#define checkRoot(root)
#else
void checkRoot(void** root);
#endif

void trace_main(void)
{
  void* root = NULL;
"""
    handleMap = dict() # index -> variable name
    sizeMap = dict() # index -> size of allocation
    while line:
      strippedline = line.strip()
      result = regex.match(strippedline)
      if result:
        funcIdx = int(result.group('idx'))
        ptr = result.group('ptr')
        size = int(result.group('size'))
        num = int(result.group('num'))
        retptr = result.group('retptr')
        isFatalIssueOccurred = False
        code_frag += "\n  /* line {0}: {1} */".format(str(lc), strippedline)
        if funcIdx == 0 or (funcIdx == 2 and ptr == name_null): # malloc or realloc(null, ...)
          if renamer.isNameUsed(retptr):
            # the allocator allocates an object on top of existing one
            index = renamer.forceAllocate_NoRecycling()
            isFatalIssueOccurred = True
          else:
            index = renamer.allocate(retptr)
            sizeMap[index] = size
          # generate malloc call
          ptrValueName = generatePtrName(lc)
          handleMap[index] = ptrValueName
          code_frag += """
  void* {0} = ifp_test_malloc(&root, {1});
  void* addr_{0} = CLEAN_PTR({0});
  objectAllocated({2}, {1}, addr_{0});
  data_check();
  checkRoot(&root);
""".format(ptrValueName, str(size), str(index))
          if isFatalIssueOccurred:
            code_frag += "\n  /* fatal error at line {0}: returned pointer is already in use */\n".format(str(lc))
        elif funcIdx == 2: # realloc
          if renamer.isNameUsed(ptr):
            # valid realloc
            ptrValueName = generatePtrName(lc)
            oldIndex = renamer.getIndex(ptr)
            oldPtrValueName = handleMap[oldIndex]
            oldSize = sizeMap[oldIndex]
            smallerSize = min(oldSize, size)
            renamer.release(ptr)
            newIndex = renamer.allocate(retptr)
            code_frag += """
  void* {0} = ifp_test_malloc(&root, {1});
  data_check();
  checkRoot(&root);
  void* addr_{0} = CLEAN_PTR({0});
  memcpy(addr_{0}, addr_{2}, {3});
  ifp_test_free({2});
  objectMoved({4}, {5}, {6}, addr_{0});
  data_check();
  checkRoot(&root);
""".format(ptrValueName, str(size), oldPtrValueName, str(smallerSize), str(oldIndex), str(newIndex), str(size))
            handleMap[newIndex] = ptrValueName
            sizeMap[newIndex] = size
          else:
            # realloc'ing a pointer not seen before
            # just print a log and do not add the event
            code_frag += "\n  /* warning at line {0}: argument pointer to realloc() not seen before; skipped */\n".format(str(lc))
        elif funcIdx == 5: # free
          if ptr != name_null:
            if renamer.isNameUsed(ptr):
              # valid free
              index = renamer.getIndex(ptr)
              ptrValueName = handleMap[index]
              code_frag += """
  ifp_test_free({0});
  objectDeallocated({1});
  data_check();
  checkRoot(&root);
""".format(ptrValueName, index)
              renamer.release(ptr)
        if isFatalIssueOccurred:
          break
      else:
        raise RuntimeError("line {}: trace not matching given regex".format(lc))
      line = f.readline()
      lc += 1
    
    # done reading the file
    code_frag += "\n}\n"
    code_frag += "\n#define NUM_PTRS {}\n".format(str(renamer.numPtrs))
    with open(outputFileName, 'w') as outf:
      outf.write(code_frag)

if __name__ == "__main__":
  traceName = 'trace.txt'
  if (len(sys.argv) > 1):
    traceName = sys.argv[1] 
  processTrace(traceName, 'trace.inc')
