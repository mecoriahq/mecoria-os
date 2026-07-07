# Publisher Agent Checklist

## Architecture

- [x] Responsibility defined
- [x] Input contract defined
- [x] Output contract defined
- [x] Schema defined
- [x] Execution Context dependency defined
- [x] Image QA approval dependency defined

## Implementation

- [ ] output.py
- [ ] run.py
- [ ] JSON validation
- [ ] Archive system
- [ ] Production test

## Quality

- [ ] Reads Script output
- [ ] Reads SEO output
- [ ] Reads Image Generation output
- [ ] Reads Image QA output
- [ ] Reads Execution Context
- [ ] Stops if Image QA is not approved
- [ ] Stops if Execution Context next_agent is not publisher
- [ ] Produces publishing package
- [ ] Runtime output ignored by Git