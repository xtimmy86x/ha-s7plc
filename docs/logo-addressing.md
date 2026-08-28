# Siemens LOGO! addressing profiles

## Authoritative sources

The fixed mappings in `logo_address.py` are transcribed exclusively from the
Siemens **LOGO!Soft Comfort Online Help**, section **Tools → Parameter VM
Mapping (0BA7 and later versions only)**. The current help contains distinct
mapping tables for LOGO! 9, LOGO! 0BA8, and LOGO! 0BA7:

* document ID 110001064, table revision available on 2026-08-28:
  <https://support.industry.siemens.com/cs/mdm/110001064?c=196445430283&t=1&s=Vm&lc=en-DE>
* the earlier Siemens online-help edition, document ID 100782807, was retained
  as a historical cross-check for 0BA7/0BA8:
  <https://support.industry.siemens.com/cs/mdm/100782807?c=85315142923&lc=en-US>

No forum, blog, vendor summary, or third-party mapping table is used.

## Implemented fixed areas

| Profile | Digital elements | Integer analog elements | Float elements |
| --- | --- | --- | --- |
| LOGO! 0BA7 | I1-I24, Q1-Q16, M1-M27 | AI1-AI8, AQ1-AQ2, AM1-AM16 | — |
| LOGO! 0BA8 | I1-I64, Q1-Q64, M1-M112, NI1-NI128, NQ1-NQ128 | AI1-AI16, AQ1-AQ16, AM1-AM64, NAI1-NAI64, NAQ1-NAQ32 | — |
| LOGO! 9 | I1-I128, Q1-Q118, M1-M240, NI1-NI640, NQ1-NQ608 | AI1-AI32, AQ1-AQ32, AM1-AM192, NAI1-NAI192, NAQ1-NAQ160, NFAI1-NFAI32, NFAQ1-NFAQ32 | FAM1-FAM32 |

LOGO! 9 uses discontinuous VM segments. For example, I1-I64 occupy bytes
1024-1031 and I65-I128 occupy bytes 6024-6031. Each segment is represented
explicitly; conversion never applies a formula across the reserved gap. The
same approach is used for Q, M, AM, NI, NAI, NQ, and NAQ.

The LOGO! 9 Q extension row is internally inconsistent: Siemens prints the
end address as `6110.5` (54 addressable bits from byte 6104) but describes the
range as 7.5 bytes (60 bits). To avoid inventing six mappings, only Q65-Q118,
which are confirmed by the printed endpoints, are implemented. Q119-Q124 stay
manual until Siemens clarifies the row.

Digital values use canonical `DB1,X<byte>.<bit>` addresses. Fixed integer
analog areas use canonical `DB1,INT<byte>` addresses: Siemens documents the
visible analog range as -32768 to 32767, and `WORD` would decode negative
two's-complement values as 32768-65535. LOGO! 9 floating analog flags use
canonical four-byte `REAL` addresses. Explicit advanced `VW` input remains a
raw unsigned `WORD` view.

## Manual parameter VM mapping

The official help documents configurable block-parameter addresses from 0 to
850. The advanced parser therefore accepts `V<byte>.<bit>`, `VB<byte>`,
`VW<byte>`, and `VD<byte>` only where the complete value fits in V0-V850.
User-assigned block parameters have no universal symbolic mapping and remain in
manual/advanced mode.

## Read/write metadata

The fixed I/O-to-VM overview identifies block types and byte ranges but does not
assign read/write permissions to each fixed area. Profiles consequently expose
`writable: null` rather than inferring permissions. The separate parameter
settings table does document R/RW per manually selected function-block
parameter, but those user-configured mappings are deliberately not generated
as universal addresses.
