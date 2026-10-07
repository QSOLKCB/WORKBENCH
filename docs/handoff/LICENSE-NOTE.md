# Licensing and source use

This handoff contains original prototype implementation and report text prepared for the user's project. It does not select a repository-wide public release license on the user's behalf.

The reviewed external repositories are linked and their source file hashes recorded; their full codebases are not included in this ZIP. The real CONTROL smoke check executed a separately downloaded public snapshot outside the handoff directory. Its returned health/capability data is included as validation evidence.

The prototype uses Python's standard library at runtime and the browser's native APIs. Node and Chrome are optional development tools used for browser validation; neither is bundled. The optional QEC/CONTROL integrations invoke operator-installed project code. The Ollama module uses its documented local HTTP API; no model weights are bundled.

If later development incorporates source from QEC, RIVET, Browsh or another project, record the exact donor files and their applicable license/notice material at that time. Do not infer that an architectural resemblance means code was copied, or that a handoff checksum supplies a software license.
