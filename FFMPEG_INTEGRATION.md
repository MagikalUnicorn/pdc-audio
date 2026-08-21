# FFmpeg integration assessment

## Conclusion

The codec is suitable for FFmpeg, but **a libavcodec decoder alone would not decode these Sony ASF files**. `SEMC PDC-AUDIO` is an ASF Extended Content Description `BYTE_ARRAY`, not an ASF media stream. FFmpeg's ASF demuxer currently recognizes byte arrays only for `WM/Picture` and `ID3`; other byte-array tags are skipped. Therefore the integration requires both:

1. a PDC half-rate / PSI-CELP decoder in `libavcodec`; and
2. Sony-specific extraction in the ASF demuxer that promotes this byte array to a synthetic audio stream.

These should be separate patches so the codec core is not coupled to Sony's storage wrapper.

## Recommended packet boundary

Define one decoder packet per 40 ms speech frame, producing 320 mono samples at 8 kHz.

The cleanest division of responsibility is:

### ASF demuxer

- recognize the exact descriptor name `SEMC PDC-AUDIO`;
- copy and validate the 16-byte Sony object header;
- divide the declared payload into 24-byte Sony records;
- identify and omit the terminal marker and zero records;
- expose an audio stream with a new codec ID and `sample_rate = 8000`, mono layout, and a 40 ms packet duration;
- emit the original 24-byte record as the packet payload, or convert it to a documented canonical PDC packet format;
- set PTS values at 0, 320, 640, ... in a `1/8000` time base.

### Decoder

- unpack the 147 meaningful Sony record bits when the stream declares Sony packing, or accept a canonical PDC frame packing;
- validate the 9-bit CRC;
- reconstruct the 138 codec parameter bits;
- decode one frame to 320 samples;
- preserve LSP, ACB and synthesis-filter state across packets;
- flush/reset all state in the decoder flush callback.

The two non-speech records should be handled by the Sony demuxing layer, not interpreted by the generic codec.

## Codec identity and packing

There are two plausible upstream designs.

### Preferred: generic `AV_CODEC_ID_PDC`

Use a generic PDC half-rate codec ID and describe the packet representation. The Sony demuxer signals its record packing through small extradata or converts each Sony record into a canonical bit order. This leaves room for future PDC sources that do not use Sony's wrapper.

### Simpler first implementation: `AV_CODEC_ID_SEMC_PDC_AUDIO`

Let the decoder accept Sony's exact 24-byte records. This is easier to implement and test, but it mixes the standardized PSI-CELP codec with one proprietary storage format and is less attractive architecturally.

A sensible compromise is `AV_CODEC_ID_PDC` with a one-byte extradata packing version, initially supporting only `SEMC_24BYTE`.

## Returning synthetic packets in timestamp order

The complete audio payload is available while the ASF header is parsed, whereas video packets are in the ASF Data Object. Returning all audio frames immediately would place packets through 6.32 seconds before the first video packet and violate normal cross-stream timestamp ordering.

The ASF demuxer should therefore keep:

- the next synthetic audio-frame index; and
- one queued real ASF packet.

`read_packet()` can obtain or retain the next real packet, compare its timestamp with the next synthetic audio timestamp, and return whichever is earlier. At end of the ASF Data Object it drains any remaining synthetic audio frames. This gives ordinary interleaved output without modifying the original file.

An aggregate one-packet design would be easier, but it would produce a multi-second audio frame, weaken seeking, blur codec/container responsibilities and be less likely to be accepted upstream.

## Decoder implementation in libavcodec

Likely files:

```text
libavcodec/pdcdec.c
libavcodec/pdcdata.h
```

FFmpeg already provides reusable CELP primitives, including floating-point and fixed-point `1/A(z)` LP synthesis. The PDC-specific implementation still needs its own:

- LSP, power, gain, FCB and two-channel stochastic codebooks;
- protected-bit/CRC mapping;
- lag and SCB transmission mappings;
- PDC fractional ACB interpolation and duplicate-position precedence;
- PSI reconstruction;
- LSP stabilization and subframe interpolation;
- state management.

A first decoder should output planar or packed float mono, matching the audited Python equations. A later patch could introduce fixed-point arithmetic if reference vectors become available. The optional postfilter should be omitted initially because it is explicitly optional and did not materially improve the listening tests.

## Registration work

A native decoder patch would normally include:

- a new `AVCodecID` near similar speech codecs;
- a codec descriptor entry;
- decoder registration and build-system entries;
- a libavcodec minor-version bump;
- documentation and Changelog entry;
- FATE tests.

## FATE testing

At minimum:

1. a raw one-frame or short multi-frame decoder test with expected PCM MD5;
2. an ASF demux test showing a video stream plus the promoted PDC audio stream;
3. CRC rejection or concealment behavior for a damaged record;
4. flush/reset behavior;
5. a test ensuring the final two Sony records are not decoded as speech.

The current clips could supply a compact sample only with the owner's permission to redistribute it in FFmpeg's FATE sample collection. An official ARIB reference vector would be substantially better.

## Preserving the original BYTE_ARRAY when remuxing

This is a separate problem from decoding. FFmpeg stores ordinary metadata in string dictionaries, while the ASF muxer writes those entries as Unicode values. It currently has no general binary-metadata passthrough path for an arbitrary Extended Content Description byte array.

Possible approaches, in increasing scope:

1. **Decode only:** support playback/transcoding but do not promise preservation on ASF remux.
2. **ASF-private attachment stream:** expose the original byte array as a `BIN_DATA` attachment stream in addition to the synthetic audio stream, and teach the ASF muxer to serialize that particular attachment back as `SEMC PDC-AUDIO`.
3. **Format-specific side data:** add an ASF-specific binary metadata representation that survives demux/remux. This is cleaner for the container but requires a more general API design.
4. **Muxer option taking an external blob:** easiest technically but not automatic passthrough and unlikely to be the preferred upstream interface.

For a first FFmpeg submission, decoder plus demux support should be proposed without claiming remux preservation. A follow-up patch can address binary ASF metadata after maintainers agree on the representation.

## Suggested patch series

```text
1/4 avcodec: add PDC half-rate / PSI-CELP decoder
2/4 avformat/asfdec: recognize Sony SEMC PDC-AUDIO byte arrays
3/4 avformat/asfdec: interleave synthetic PDC packets with ASF media packets
4/4 fate: add PDC decoder and Sony ASF demux tests
```

A separate later series could add ASF binary-metadata preservation.

## Upstream risks

- no official bit-exact vector yet;
- unspecified reset/fixed-point details in the available public text;
- provenance and licensing review for the large numerical codebook tables;
- only five files from one handset model currently tested;
- the Sony trailer semantics remain empirical;
- FATE sample redistribution permission would be needed.

None of these makes integration unsuitable, but they argue for presenting the decoder as an error-free, floating-point implementation backed by tests rather than claiming reference bit-exactness.
