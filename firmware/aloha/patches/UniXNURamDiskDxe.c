/** @file
  Publish the boot payload as a read-only block device.

  Two discovery paths, in order:

  1. Mu-Silicium hands the incoming x0 to DXE as a GUID HOB and that value is
     the device tree, with /chosen/linux,initrd-start and -end.
  2. LG's abl puts the ramdisk address in x0 instead of the device tree. In
     that case the value points straight at the payload image, so the FAT boot
     sector is read in place to size the volume.

  A short status line is kept in a UEFI variable so a firmware without a serial
  port can still say where discovery stopped (the UniXNU menu prints it).

  SPDX-License-Identifier: BSD-2-Clause
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/PrintLib.h>
#include <Library/FdtLib.h>
#include <Library/HobLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>

// Mu-Silicium SEC stores the incoming x0 value in this HOB as a UINT64.
STATIC CONST EFI_GUID mEntryArgHobGuid = {
  0xDAEE82E6, 0x8090, 0x4E72, { 0xBF, 0xB9, 0x78, 0xC1, 0x3C, 0xD4, 0xE3, 0x59 }
};

STATIC CONST EFI_GUID mStatusGuid = {
  0x6b3f3a11, 0x2f7c, 0x4a55, { 0x9a, 0x11, 0x7d, 0x3c, 0x55, 0x66, 0x77, 0x88 }
};

STATIC
VOID
SetStatus (
  IN CONST CHAR16  *Text
  )
{
  gRT->SetVariable (
         L"UnixnuRamDisk",
         (EFI_GUID *)&mStatusGuid,
         0x00000002 | 0x00000001,
         StrSize (Text),
         (VOID *)Text
         );
}

STATIC
UINT64
ReadCells (
  IN CONST VOID  *Data,
  IN UINT32      Cells
  )
{
  if (Cells == 2) {
    return Fdt64ToCpu (ReadUnaligned64 (Data));
  }

  return Fdt32ToCpu (ReadUnaligned32 (Data));
}

#define RAM_BLOCK_SIZE  512

#pragma pack(1)
typedef struct {
  VENDOR_DEVICE_PATH          Vendor;
  EFI_DEVICE_PATH_PROTOCOL    End;
} RAM_BLOCK_DEVICE_PATH;
#pragma pack()

STATIC RAM_BLOCK_DEVICE_PATH  mDevicePath = {
  {
    { HARDWARE_DEVICE_PATH, HW_VENDOR_DP, { (UINT8)sizeof (VENDOR_DEVICE_PATH), (UINT8)(sizeof (VENDOR_DEVICE_PATH) >> 8) } },
    { 0xA9C6827C, 0x1BD8, 0x410C, { 0x88, 0x5A, 0xC4, 0x65, 0x00, 0xF7, 0xD8, 0x36 } }
  },
  { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { sizeof (EFI_DEVICE_PATH_PROTOCOL), 0 } }
};

STATIC UINT8               *mRamBase;
STATIC EFI_BLOCK_IO_MEDIA  mMedia;
STATIC EFI_HANDLE          mHandle;

STATIC
EFI_STATUS
EFIAPI
RamBlockReset (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN BOOLEAN                ExtendedVerification
  )
{
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockRead (
  IN  EFI_BLOCK_IO_PROTOCOL  *This,
  IN  UINT32                 MediaId,
  IN  EFI_LBA                Lba,
  IN  UINTN                  BufferSize,
  OUT VOID                   *Buffer
  )
{
  if (Buffer == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  if (MediaId != mMedia.MediaId) {
    return EFI_MEDIA_CHANGED;
  }

  if ((BufferSize % RAM_BLOCK_SIZE) != 0) {
    return EFI_BAD_BUFFER_SIZE;
  }

  if ((Lba > mMedia.LastBlock) || ((BufferSize / RAM_BLOCK_SIZE) > (mMedia.LastBlock + 1 - Lba))) {
    return EFI_INVALID_PARAMETER;
  }

  CopyMem (Buffer, mRamBase + Lba * RAM_BLOCK_SIZE, BufferSize);
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockWrite (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN UINT32                 MediaId,
  IN EFI_LBA                Lba,
  IN UINTN                  BufferSize,
  IN VOID                   *Buffer
  )
{
  return EFI_WRITE_PROTECTED;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockFlush (
  IN EFI_BLOCK_IO_PROTOCOL  *This
  )
{
  return EFI_SUCCESS;
}

STATIC EFI_BLOCK_IO_PROTOCOL  mBlockIo = {
  EFI_BLOCK_IO_PROTOCOL_REVISION,
  &mMedia,
  RamBlockReset,
  RamBlockRead,
  RamBlockWrite,
  RamBlockFlush
};

STATIC
EFI_STATUS
PublishRange (
  IN UINT64  Start,
  IN UINT64  Size
  )
{
  EFI_STATUS  Status;

  mRamBase                = (UINT8 *)(UINTN)Start;
  mMedia.MediaId          = 1;
  mMedia.RemovableMedia   = FALSE;
  mMedia.MediaPresent     = TRUE;
  mMedia.LogicalPartition = FALSE;
  mMedia.ReadOnly         = TRUE;
  mMedia.WriteCaching     = FALSE;
  mMedia.BlockSize        = RAM_BLOCK_SIZE;
  mMedia.IoAlign          = 1;
  mMedia.LastBlock        = Size / RAM_BLOCK_SIZE - 1;
  mHandle                 = NULL;

  Status = gBS->InstallMultipleProtocolInterfaces (
                  &mHandle,
                  &gEfiDevicePathProtocolGuid,
                  &mDevicePath,
                  &gEfiBlockIoProtocolGuid,
                  &mBlockIo,
                  NULL
                  );
  return Status;
}

/**
  Treat Base as the start of a FAT image and publish it when the boot sector
  looks sane. LG's abl passes the ramdisk address in x0; there is no device
  tree to ask for the length, so the BPB supplies it.
**/
STATIC
BOOLEAN
TryFatImage (
  IN UINT64  Base
  )
{
  CONST UINT8  *Boot;
  UINT16       BytesPerSector;
  UINT8        SectorsPerCluster;
  UINT16       Total16;
  UINT32       Total32;
  UINT64       TotalSectors;
  UINT64       Size;
  CHAR16       Done[72];

  if ((Base == 0) || ((Base & 0x1FF) != 0)) {
    return FALSE;
  }

  Boot = (CONST UINT8 *)(UINTN)Base;
  if ((Boot[510] != 0x55) || (Boot[511] != 0xAA)) {
    return FALSE;
  }

  BytesPerSector    = ReadUnaligned16 ((CONST UINT16 *)(Boot + 11));
  SectorsPerCluster = Boot[13];
  Total16           = ReadUnaligned16 ((CONST UINT16 *)(Boot + 19));
  Total32           = ReadUnaligned32 ((CONST UINT32 *)(Boot + 32));
  TotalSectors      = (Total16 != 0) ? Total16 : Total32;

  if ((BytesPerSector != 512) || (SectorsPerCluster == 0) || (TotalSectors == 0)) {
    return FALSE;
  }

  Size = TotalSectors * 512ULL;
  if ((Size < (1ULL << 20)) || (Size > (256ULL << 20))) {
    return FALSE;
  }

  if (EFI_ERROR (PublishRange (Base, Size))) {
    return FALSE;
  }

  UnicodeSPrint (Done, sizeof (Done), L"rd: fat 0x%lx+0x%lx", Base, Size);
  SetStatus (Done);
  return TRUE;
}

/**
  Sweep the reserved kernel window for a FAT boot sector.

  The bootloader places the initrd somewhere in the Kernel region reserved by
  PlatformMemoryMapLib (0x80000000 + 42 MiB on this board) but this abl does
  not tell us where: x0 is neither the device tree nor the ramdisk. Reading the
  window is safe because the whole window is DRAM described to DXE.
**/
STATIC
UINT64
ScanFatImage (
  VOID
  )
{
  UINT64       Base;
  CONST UINT8  *Boot;

  for (Base = 0x80000000ULL; Base < 0x82A00000ULL; Base += 0x1000) {
    Boot = (CONST UINT8 *)(UINTN)Base;
    if ((Boot[510] == 0x55) && (Boot[511] == 0xAA) &&
        (Boot[54] == 'F') && (Boot[55] == 'A') && (Boot[56] == 'T'))
    {
      return Base;
    }
  }

  return 0;
}

STATIC
VOID
PublishInitrd (
  IN CONST VOID  *Fdt
  )
{
  EFI_STATUS  Status;
  INT32       Chosen;
  CONST VOID  *StartProp;
  CONST VOID  *EndProp;
  INT32       StartLength;
  INT32       EndLength;
  UINT64      Start;
  UINT64      End;

  Chosen = FdtPathOffset (Fdt, "/chosen");
  if (Chosen < 0) {
    SetStatus (L"rd: dtb ok, no /chosen");
    return;
  }

  StartProp = FdtGetProp (Fdt, Chosen, "linux,initrd-start", &StartLength);
  EndProp   = FdtGetProp (Fdt, Chosen, "linux,initrd-end", &EndLength);
  if ((StartProp == NULL) || (EndProp == NULL) ||
      ((StartLength != 4) && (StartLength != 8)) ||
      ((EndLength != 4) && (EndLength != 8)))
  {
    SetStatus (L"rd: /chosen has no initrd props");
    return;
  }

  Start = ReadCells (StartProp, StartLength / 4);
  End   = ReadCells (EndProp, EndLength / 4);
  if ((End <= Start) || (((End - Start) % RAM_BLOCK_SIZE) != 0)) {
    SetStatus (L"rd: initrd range is not sector sized");
    return;
  }

  Status = PublishRange (Start, End - Start);
  {
    CHAR16  Done[72];
    UnicodeSPrint (Done, sizeof (Done), L"rd: dtb 0x%lx+0x%lx %r", Start, End - Start, Status);
    SetStatus (Done);
  }
}

EFI_STATUS
EFIAPI
UniXNURamDiskDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_HOB_GUID_TYPE  *Hob;
  UINT64             X0;
  CHAR16             Why[80];

  SetStatus (L"rd: starting");

  Hob = GetFirstGuidHob (&mEntryArgHobGuid);
  if (Hob == NULL) {
    SetStatus (L"rd: no entry-arg HOB");
    return EFI_SUCCESS;
  }

  if (GET_GUID_HOB_DATA_SIZE (Hob) < sizeof (UINT64)) {
    SetStatus (L"rd: HOB too small");
    return EFI_COMPROMISED_DATA;
  }

  X0 = ReadUnaligned64 ((CONST UINT64 *)GET_GUID_HOB_DATA (Hob));

  if ((X0 != 0) && ((X0 & 3) == 0) && (FdtCheckHeader ((VOID *)(UINTN)X0) == 0)) {
    UnicodeSPrint (Why, sizeof (Why), L"rd: dtb 0x%lx", X0);
    SetStatus (Why);
    PublishInitrd ((VOID *)(UINTN)X0);
    return EFI_SUCCESS;
  }

  if (TryFatImage (X0)) {
    return EFI_SUCCESS;
  }

  if (TryFatImage (0x80800000ULL) || TryFatImage (0x81000000ULL)) {
    return EFI_SUCCESS;
  }

  {
    UINT64  Found = ScanFatImage ();
    if (Found != 0) {
      UnicodeSPrint (Why, sizeof (Why), L"rd: scan hit 0x%lx", Found);
      SetStatus (Why);
      TryFatImage (Found);
      return EFI_SUCCESS;
    }
  }

  UnicodeSPrint (Why, sizeof (Why), L"rd: x0=0x%lx, scan found no fat", X0);
  SetStatus (Why);
  return EFI_SUCCESS;
}
