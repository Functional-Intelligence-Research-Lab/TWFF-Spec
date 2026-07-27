# Contributing

TWFF is an open standard. Contributions from researchers, developers, and educators are welcome.

## How to contribute

1. Open an issue to propose a spec change, before writing code against it.
2. Build tools, libraries, or integrations against the current spec.
3. Use TWFF in your own research or classroom, and report back what worked or didn't.

## Repo structure

```text
twff/
├── README.md
├── LICENSE                    Apache 2.0
├── spec/
│   ├── SPEC.md                 Normative spec (current: v0.2)
│   ├── process-log.schema.json JSON Schema for process-log.json
│   ├── manifest.xsd             XML Schema for manifest.xml
│   ├── v0.1/                    Frozen v0.1 release
│   └── v0.2/                    Version marker for the current spec
└── glassbox/                  Reference implementation
```
