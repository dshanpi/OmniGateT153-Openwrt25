// Offline harness. No USB, FES or flash functions are linked or executed.
// extract_mainline_spl below is byte-for-byte from the recorded upstream commit.
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

#[derive(Debug)]
enum FlashError {
    Io(std::io::Error),
    InvalidFirmwareFormat(String),
}
type FlashResult<T> = Result<T, FlashError>;

const MAINLINE_SPL_DISK_OFFSET: u64 = 8 * 1024;
const MAINLINE_SPL_MAX_BYTES: usize = 1024 * 1024;

fn extract_mainline_spl(path: &Path, image_len: u64) -> FlashResult<Vec<u8>> {
    if image_len < MAINLINE_SPL_DISK_OFFSET + 0x20 {
        return Err(FlashError::InvalidFirmwareFormat(
            "EMMC_BOOT0_IMAGE_TOO_SMALL".to_owned(),
        ));
    }
    let mut file = File::open(path).map_err(FlashError::Io)?;
    file.seek(SeekFrom::Start(MAINLINE_SPL_DISK_OFFSET))
        .map_err(FlashError::Io)?;
    let mut header = [0_u8; 0x20];
    file.read_exact(&mut header).map_err(FlashError::Io)?;
    if header.get(4..12) != Some(b"eGON.BT0") || header.get(0x14..0x17) != Some(b"SPL") {
        return Err(FlashError::InvalidFirmwareFormat(
            "EMMC_BOOT0_MAINLINE_SPL_REQUIRED:image offset 0x2000 has no eGON.BT0 SPL".to_owned(),
        ));
    }
    let version = header[0x17];
    if !(1..=31).contains(&version) {
        return Err(FlashError::InvalidFirmwareFormat(format!(
            "EMMC_BOOT0_SPL_VERSION_UNSUPPORTED:{version}"
        )));
    }
    let length = u32::from_le_bytes(header[0x10..0x14].try_into().expect("four bytes")) as usize;
    if !(0x20..=MAINLINE_SPL_MAX_BYTES).contains(&length)
        || !length.is_multiple_of(4)
        || MAINLINE_SPL_DISK_OFFSET + length as u64 > image_len
    {
        return Err(FlashError::InvalidFirmwareFormat(format!(
            "EMMC_BOOT0_SPL_LENGTH_INVALID:{length}"
        )));
    }
    let mut spl = vec![0_u8; length];
    spl[..header.len()].copy_from_slice(&header);
    file.read_exact(&mut spl[header.len()..])
        .map_err(FlashError::Io)?;
    let stored = u32::from_le_bytes(spl[0x0c..0x10].try_into().expect("four bytes"));
    let expected_sum = stored.wrapping_mul(2).wrapping_sub(0x5f0a_6c39);
    let actual_sum = spl.chunks_exact(4).fold(0_u32, |sum, word| {
        sum.wrapping_add(u32::from_le_bytes(word.try_into().expect("four bytes")))
    });
    if actual_sum != expected_sum {
        return Err(FlashError::InvalidFirmwareFormat(
            "EMMC_BOOT0_SPL_CHECKSUM_INVALID".to_owned(),
        ));
    }

    Ok(spl)
}

fn main() {
    let path_arg = std::env::args_os().nth(1).expect("usage: offline-harness raw.img");
    let path = Path::new(&path_arg);
    let image_len = std::fs::metadata(path).expect("image metadata").len();
    match extract_mainline_spl(path, image_len) {
        Ok(spl) => {
            let stored = u32::from_le_bytes(spl[0x0c..0x10].try_into().unwrap());
            let actual_sum = spl.chunks_exact(4).fold(0_u32, |sum, word| {
                sum.wrapping_add(u32::from_le_bytes(word.try_into().unwrap()))
            });
            let expected_sum = stored.wrapping_mul(2).wrapping_sub(0x5f0a6c39);
            let header_hex: String = spl[..96].iter().map(|v| format!("{v:02x}")).collect();
            println!("{{\"status\":\"PASS\",\"image_bytes\":{image_len},\"spl_offset\":{MAINLINE_SPL_DISK_OFFSET},\"spl_length\":{},\"spl_header_version\":{},\"stored_checksum\":{stored},\"actual_sum_with_stored\":{actual_sum},\"expected_sum_with_stored\":{expected_sum},\"header_hex\":\"{header_hex}\"}}", spl.len(), spl[0x17]);
        }
        Err(error) => {
            eprintln!("FAIL: {error:?}");
            std::process::exit(1);
        }
    }
}
