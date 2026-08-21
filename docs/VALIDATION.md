# v3.3 validation

> Historical validation record imported from `snapshot-v3.3-final-asf`.

The production workflow was run against all five supplied Sony SO505i clips (130–134).

For every clip:

- 158 of 160 stored records were decoded as active speech records;
- all 158 active records passed the PDC 9-bit CRC;
- the output duration was 6.400 seconds;
- FFprobe reported MJPEG video at 160×120 and 5 fps;
- FFprobe reported mono `pcm_s16le` audio at 8 kHz;
- the source and output video packet SHA-256 hashes matched;
- the decoded WAV and output PCM packet SHA-256 hashes matched;
- the complete `SEMC PDC-AUDIO` descriptor entry matched byte-for-byte.

| Clip | MJPEG packet SHA-256 | PCM packet SHA-256 |
|---|---|---|
| 130 | `8901d83731b0f9406f623a7f108195f25de3c66fa18a51434f531fda34fbec3f` | `cc4dfef72a59434d06d4140296bfb0af1ef7ecfc2cb97ebc98019bc1771b73eb` |
| 131 | `220de7b40c1a8961ef2997d94dab75b15ae3e811e7fab400d24aca253f4ba82c` | `95d882b1a1ceec0c4a3c5fa20022a9ced400873a834e32869d7a99ab8bd5c7f2` |
| 132 | `fbb752290f73c684ed5c3a8682e0881edf9c65a7e1af1c5e392a425fb1667ffc` | `d4a02d75f0cf19f0cbdac04095d2e4c9fb3fd12555b06f58c05c01c65e199198` |
| 133 | `9ffad63a5d364aee2d2542b064945c052cf197d1438e46c1bc59170f54b673a1` | `e1f11e19b1c6a256f138be54d228e07e8cf5eee8074efb12acbf87c08c3bc63d` |
| 134 | `13027b3ae2abfe90013c5b3401cea8ec966e399ba6f6924754e6fbfb01542301` | `bd0852237dfdee4f2bbabb2f62578501740b1a93f17f5d0d7644665683bf3bff` |

The v3.3 release changes the container workflow only. The decoder waveform is the frozen v3/v3.2 core.
