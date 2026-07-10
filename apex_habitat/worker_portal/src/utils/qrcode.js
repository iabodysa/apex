// Copyright (c) 2026, AFMCO and contributors
// Dependency-free QR encoder (byte mode, ECC level M, versions 1..14) so the SPA
// renders the boarding-pass token without pulling a QR library. Per ISO/IEC 18004.

// GF(256) tables (primitive polynomial 0x11d).
const EXP = new Array(512);
const LOG = new Array(256);
(function initGF() {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
})();

function gfMul(a, b) {
  if (a === 0 || b === 0) return 0;
  return EXP[LOG[a] + LOG[b]];
}

// Generator polynomial of degree ecLen, monic, coefficients in DESCENDING degree
// (gen[0] = leading x^ecLen term = 1). Product of (x - α^i) for i in 0..ecLen-1.
function rsGenerator(ecLen) {
  let gen = [1];
  for (let i = 0; i < ecLen; i++) {
    // multiply gen(x) by (x + α^i): shift up by one degree, add α^i * gen.
    const next = new Array(gen.length + 1).fill(0);
    for (let j = 0; j < gen.length; j++) {
      next[j] ^= gen[j]; // the x * gen term
      next[j + 1] ^= gfMul(gen[j], EXP[i]); // the α^i * gen term
    }
    gen = next;
  }
  return gen;
}

// Reed–Solomon ECC bytes for a data block (polynomial division remainder).
function rsEncode(data, ecLen) {
  const gen = rsGenerator(ecLen); // length ecLen+1, gen[0] = 1
  const res = new Array(ecLen).fill(0);
  for (let i = 0; i < data.length; i++) {
    const factor = data[i] ^ res[0];
    res.shift();
    res.push(0);
    if (factor !== 0) {
      // subtract factor * gen (skip the leading gen[0]=1, already consumed)
      for (let j = 0; j < ecLen; j++) res[j] ^= gfMul(gen[j + 1], factor);
    }
  }
  return res;
}

// Per-version capacity / block layout for ECC level M (versions 1..14).
// [totalCodewords, ecPerBlock, group1Blocks, group1DataCw, group2Blocks, group2DataCw]
const VERSION_M = {
  1: [26, 10, 1, 16, 0, 0],
  2: [44, 16, 1, 28, 0, 0],
  3: [70, 26, 1, 44, 0, 0],
  4: [100, 18, 2, 32, 0, 0],
  5: [134, 24, 2, 43, 0, 0],
  6: [172, 16, 4, 27, 0, 0],
  7: [196, 18, 4, 31, 0, 0],
  8: [242, 22, 2, 38, 2, 39],
  9: [292, 22, 3, 36, 2, 37],
  10: [346, 26, 4, 43, 1, 44],
  11: [404, 30, 1, 50, 4, 51],
  12: [466, 22, 6, 36, 2, 37],
  13: [532, 22, 8, 37, 1, 38],
  14: [581, 24, 4, 40, 5, 41],
};

const ALIGN_POS = {
  1: [],
  2: [6, 18],
  3: [6, 22],
  4: [6, 26],
  5: [6, 30],
  6: [6, 34],
  7: [6, 22, 38],
  8: [6, 24, 42],
  9: [6, 26, 46],
  10: [6, 28, 50],
  11: [6, 30, 54],
  12: [6, 32, 58],
  13: [6, 34, 62],
  14: [6, 26, 46, 66],
};

function totalDataCodewords(v) {
  const [, ec, g1b, g1d, g2b, g2d] = VERSION_M[v];
  void ec;
  return g1b * g1d + g2b * g2d;
}

// Smallest version (1..14) whose data capacity holds `byteLen` in byte mode.
function pickVersion(byteLen) {
  for (let v = 1; v <= 14; v++) {
    const cap = totalDataCodewords(v);
    // header: 4-bit mode + length (8 bits for v1-9, 16 for v>=10), then data bytes
    const lenBits = v <= 9 ? 8 : 16;
    const needBits = 4 + lenBits + byteLen * 8;
    if (needBits <= cap * 8) return v;
  }
  throw new Error("QR payload too large");
}

// Bit buffer.
function bitBuffer() {
  const bits = [];
  return {
    put(value, length) {
      for (let i = length - 1; i >= 0; i--) bits.push((value >> i) & 1);
    },
    get bits() {
      return bits;
    },
  };
}

function buildDataCodewords(bytes, version) {
  const buf = bitBuffer();
  buf.put(0b0100, 4); // byte mode
  buf.put(bytes.length, version <= 9 ? 8 : 16);
  for (const b of bytes) buf.put(b, 8);

  const capacityBits = totalDataCodewords(version) * 8;
  // terminator (up to 4 zero bits)
  const term = Math.min(4, capacityBits - buf.bits.length);
  for (let i = 0; i < term; i++) buf.bits.push(0);
  // pad to a byte boundary
  while (buf.bits.length % 8 !== 0) buf.bits.push(0);

  const codewords = [];
  for (let i = 0; i < buf.bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | buf.bits[i + j];
    codewords.push(byte);
  }
  // pad bytes alternate 0xEC / 0x11
  const padBytes = [0xec, 0x11];
  let pi = 0;
  while (codewords.length < totalDataCodewords(version)) {
    codewords.push(padBytes[pi % 2]);
    pi++;
  }
  return codewords;
}

// Interleave data + ecc codewords across blocks per the spec.
function interleave(dataCodewords, version) {
  const [, ecLen, g1b, g1d, g2b, g2d] = VERSION_M[version];
  const blocks = [];
  let offset = 0;
  for (let i = 0; i < g1b; i++) {
    const d = dataCodewords.slice(offset, offset + g1d);
    offset += g1d;
    blocks.push({ data: d, ec: rsEncode(d, ecLen) });
  }
  for (let i = 0; i < g2b; i++) {
    const d = dataCodewords.slice(offset, offset + g2d);
    offset += g2d;
    blocks.push({ data: d, ec: rsEncode(d, ecLen) });
  }
  const result = [];
  const maxData = Math.max(g1d, g2d);
  for (let i = 0; i < maxData; i++) {
    for (const blk of blocks) if (i < blk.data.length) result.push(blk.data[i]);
  }
  for (let i = 0; i < ecLen; i++) {
    for (const blk of blocks) result.push(blk.ec[i]);
  }
  return result;
}

// Matrix placement.
function makeMatrix(size) {
  const m = [];
  for (let r = 0; r < size; r++) m.push(new Array(size).fill(null));
  return m;
}

function placeFinder(m, r, c) {
  for (let dr = -1; dr <= 7; dr++) {
    for (let dc = -1; dc <= 7; dc++) {
      const rr = r + dr;
      const cc = c + dc;
      if (rr < 0 || cc < 0 || rr >= m.length || cc >= m.length) continue;
      const inRing =
        dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6
          ? dr === 0 || dr === 6 || dc === 0 || dc === 6 || (dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4)
          : false;
      m[rr][cc] = inRing ? 1 : 0;
    }
  }
}

function placePatterns(m, version) {
  const size = m.length;
  placeFinder(m, 0, 0);
  placeFinder(m, 0, size - 7);
  placeFinder(m, size - 7, 0);

  // timing patterns
  for (let i = 8; i < size - 8; i++) {
    if (m[6][i] === null) m[6][i] = i % 2 === 0 ? 1 : 0;
    if (m[i][6] === null) m[i][6] = i % 2 === 0 ? 1 : 0;
  }

  // alignment patterns
  const pos = ALIGN_POS[version];
  for (const r of pos) {
    for (const c of pos) {
      // skip the three corners overlapping finders
      if ((r === 6 && c === 6) || (r === 6 && c === size - 7) || (r === size - 7 && c === 6))
        continue;
      for (let dr = -2; dr <= 2; dr++) {
        for (let dc = -2; dc <= 2; dc++) {
          const ring = Math.max(Math.abs(dr), Math.abs(dc));
          m[r + dr][c + dc] = ring === 1 ? 0 : 1;
        }
      }
    }
  }

  // dark module
  m[size - 8][8] = 1;

  // version information (v7+): an 18-bit BCH block placed near the top-right and
  // bottom-left finders. These are function modules, so placing them here also
  // reserves the cells from the data pass.
  if (version >= 7) {
    const bits = versionInfoBits(version);
    for (let i = 0; i < 18; i++) {
      const bit = (bits >> i) & 1;
      const r = Math.floor(i / 3);
      const c = i % 3;
      m[r][size - 11 + c] = bit; // top-right block
      m[size - 11 + c][r] = bit; // bottom-left block (transposed)
    }
  }
  return m;
}

// 18-bit version information: 6 data bits (version number) + 12 BCH(18,6) bits,
// generator polynomial 0x1f25 (ISO/IEC 18004 Annex D).
function versionInfoBits(version) {
  let rem = version;
  for (let i = 0; i < 12; i++) {
    rem <<= 1;
    if (rem & 0x1000) rem ^= 0x1f25;
  }
  return (version << 12) | rem;
}

function reserveFormatInfo(m) {
  const size = m.length;
  const mark = (r, c) => {
    if (m[r][c] === null) m[r][c] = 2; // 2 = reserved (set later)
  };
  for (let i = 0; i <= 8; i++) {
    mark(8, i);
    mark(i, 8);
  }
  for (let i = 0; i < 8; i++) {
    mark(8, size - 1 - i);
    mark(size - 1 - i, 8);
  }
}

function placeData(m, codewords) {
  const size = m.length;
  const bits = [];
  for (const cw of codewords) for (let i = 7; i >= 0; i--) bits.push((cw >> i) & 1);

  let bitIdx = 0;
  let up = true;
  for (let col = size - 1; col > 0; col -= 2) {
    // Every column pair at or left of the vertical timing line (col 6) shifts one
    // left so the timing column is skipped entirely, not just the pair on it.
    const right = col <= 6 ? col - 1 : col;
    for (let i = 0; i < size; i++) {
      const row = up ? size - 1 - i : i;
      for (let c = 0; c < 2; c++) {
        const cc = right - c;
        if (m[row][cc] === null) {
          m[row][cc] = bitIdx < bits.length ? bits[bitIdx] : 0;
          bitIdx++;
        }
      }
    }
    up = !up;
  }
}

const MASKS = [
  (r, c) => (r + c) % 2 === 0,
  (r) => r % 2 === 0,
  (r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];

// Format info (15 bits) for ECC level M + mask, with BCH error correction.
function formatBits(maskIdx) {
  const FORMAT_MASK = 0b101010000010010;
  // ECC level M = 0b00
  let data = (0b00 << 3) | maskIdx;
  let rem = data;
  for (let i = 0; i < 10; i++) {
    rem <<= 1;
    if (rem & 0b10000000000) rem ^= 0b10100110111;
  }
  const bits = ((data << 10) | rem) ^ FORMAT_MASK;
  return bits & 0x7fff;
}

function placeFormat(m, maskIdx) {
  const size = m.length;
  const bits = formatBits(maskIdx);
  // Ring position p (0..14) carries the MSB-first bit (bit 14 first); both copies
  // are placed identically per ISO/IEC 18004 §8.9.
  const get = (p) => (bits >> (14 - p)) & 1;
  // copy 1: along the top-left finder (row 8, then column 8 going up)
  for (let i = 0; i <= 5; i++) m[8][i] = get(i);
  m[8][7] = get(6);
  m[8][8] = get(7);
  m[7][8] = get(8);
  for (let i = 9; i <= 14; i++) m[14 - i][8] = get(i);
  // copy 2: column 8 under the top-right finder, then row 8 along the bottom-left
  for (let i = 0; i <= 7; i++) m[size - 1 - i][8] = get(i);
  for (let i = 8; i <= 14; i++) m[8][size - 15 + i] = get(i);
}

function penalty(m) {
  const size = m.length;
  let score = 0;
  // rule 1: runs of 5+ same colour
  const run = (get) => {
    for (let a = 0; a < size; a++) {
      let last = -1;
      let len = 0;
      for (let b = 0; b < size; b++) {
        const v = get(a, b);
        if (v === last) {
          len++;
          if (len === 5) score += 3;
          else if (len > 5) score += 1;
        } else {
          last = v;
          len = 1;
        }
      }
    }
  };
  run((a, b) => m[a][b]);
  run((a, b) => m[b][a]);
  // rule 2: 2x2 blocks
  for (let r = 0; r < size - 1; r++) {
    for (let c = 0; c < size - 1; c++) {
      const v = m[r][c];
      if (v === m[r][c + 1] && v === m[r + 1][c] && v === m[r + 1][c + 1]) score += 3;
    }
  }
  // rule 3: finder-like pattern
  const pattern = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0];
  const matchAt = (get, a, b) => {
    for (let k = 0; k < 11; k++) if (get(a, b + k) !== pattern[k]) return false;
    return true;
  };
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size - 10; c++) {
      if (matchAt((a, b) => m[a][b], r, c)) score += 40;
      if (matchAt((a, b) => m[b][a], r, c)) score += 40;
    }
  }
  // rule 4: dark/light balance
  let dark = 0;
  for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) dark += m[r][c];
  const pct = (dark / (size * size)) * 100;
  score += Math.floor(Math.abs(pct - 50) / 5) * 10;
  return score;
}

// Build the final boolean module matrix for `text`. Returns { size, modules }
// where modules[r][c] is true for a dark module.
export function encodeQr(text) {
  const bytes = [];
  // UTF-8 encode (the token is ASCII, but stay correct for any payload)
  for (const ch of unescape(encodeURIComponent(text))) bytes.push(ch.charCodeAt(0) & 0xff);

  const version = pickVersion(bytes.length);
  const dataCw = buildDataCodewords(bytes, version);
  const allCw = interleave(dataCw, version);
  const size = version * 4 + 17;

  // function-module map: build the patterns once, remember which cells are function.
  const base = makeMatrix(size);
  placePatterns(base, version);
  reserveFormatInfo(base);
  const isFunction = base.map((row) => row.map((v) => v !== null));

  placeData(base, allCw);
  // base now holds function modules (0/1/2-reserved) + data bits (0/1).

  // try all 8 masks, pick the lowest penalty
  let best = null;
  let bestScore = Infinity;
  for (let mi = 0; mi < 8; mi++) {
    const cand = base.map((row) => row.slice());
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        if (!isFunction[r][c] && MASKS[mi](r, c)) cand[r][c] ^= 1;
      }
    }
    placeFormat(cand, mi);
    const sc = penalty(cand.map((row) => row.map((v) => (v === 2 ? 0 : v))));
    if (sc < bestScore) {
      bestScore = sc;
      best = cand;
    }
  }

  const modules = best.map((row) => row.map((v) => v === 1));
  return { size, modules };
}
