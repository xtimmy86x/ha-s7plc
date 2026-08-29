# Siemens LOGO! addressing profiles

## Official sources and interpretation

Mappings come from Siemens **LOGO!Soft Comfort Online Help**, **Tools →
Parameter VM Mapping**, document 110001064, and its generation-specific
variable/tag tables:
<https://support.industry.siemens.com/cs/mdm/110001064?c=196445430283&t=1&s=Vm&lc=en-DE>.
The LOGO! 9 output count is cross-checked against Siemens' delivery release,
which specifies 60 outputs:
<https://support.industry.siemens.com/cs/document/110001668/delivery-release-for-logo%21-9-basic-devices-and-logo%21-soft-comfort-v9?dti=0&lc=en-ww>.

A VM allocation is capacity, not an element count. The converter exposes only
numbered LOGO! elements. Unused bytes inside an allocated VM interval remain
reserved and reverse conversion never identifies them as an element. LOGO! 9
rows are a separate generation-specific segment, not an extension appended to
0BA8.

## Implemented elements and VM use

| Profile | Area | Elements | VM start | Bytes used | Reserved capacity after used bytes |
| --- | --- | ---: | ---: | ---: | --- |
| 0BA7 | I / AI / Q / AQ / M / AM | 24 / 8 / 16 / 2 / 27 / 16 | 923 / 926 / 942 / 944 / 948 / 952 | 3 / 16 / 2 / 4 / 4 / 32 | Per Siemens 0BA7 table |
| 0BA8 | I / AI / Q / AQ / M / AM | 24 / 8 / 20 / 8 / 64 / 64 | 1024 / 1032 / 1064 / 1072 / 1104 / 1118 | 3 / 16 / 3 / 16 / 8 / 128 | Remaining bytes up to the next official area start |
| 0BA8 | NI / NAI / NQ / NAQ | 64 / 32 / 64 / 32 | 1246 / 1262 / 1390 / 1406 | 8 / 64 / 8 / 64 | Remaining bytes up to the next official area start |
| LOGO! 9 | I / AI / Q / AQ / M / AM / FAM | 64 / 16 / 60 / 16 / 128 / 128 / 32 | 6024 / 6040 / 6104 / 6120 / 6184 / 6216 / 6728 | 8 / 32 / 8 / 32 / 16 / 256 / 128 | Gaps between official LOGO! 9 starts are reserved |
| LOGO! 9 | NI / NAI / NQ / NAQ | 512 / 128 / 480 / 128 | 6984 / 7112 / 7624 / 7752 | 64 / 256 / 60 / 256 | Gaps between official LOGO! 9 starts are reserved |
| LOGO! 9 | NFAI / NFAQ | 32 / 32 | 8264 / 8392 | 64 / 64 | Only the documented numbered ranges are exposed |

Thus 0BA8 `I24` is `DB1,X1026.7`, while `I25` is rejected even though its
allocated VM region has spare capacity. LOGO! 9 `I1` is `DB1,X6024.0`; no
0BA8 elements are prepended. Analog values use signed pyS7 `INT`, digital
values use `X`, and FAM uses `REAL`.

## Manual VM mapping and limits

User-assigned function-block parameters have no universal symbolic address and
remain manual/advanced pyS7 addresses. Raw `V`, `VB`, `VW`, and `VD` forms are
accepted only when the complete value fits V0–V850.

No undocumented LOGO! 9 area is inferred. NFAI/NFAQ are limited to the ranges
explicitly present in Siemens' table. The apparent Q end-address/length
rounding discrepancy is resolved using Siemens' independent statement of 60
physical outputs; only Q1–Q60 is exposed.
