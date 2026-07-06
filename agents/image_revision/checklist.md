# Image Revision Agent Checklist

## Architecture

- [x] Responsibility defined
- [x] Input contract defined
- [x] Output contract defined
- [x] Schema defined
- [x] Image QA rejection dependency defined

## Implementation

- [ ] output.py
- [ ] prompt.py
- [ ] run.py
- [ ] JSON validation
- [ ] Archive system
- [ ] Production test

## Quality

- [ ] Reads Image Prompt output
- [ ] Reads Image Generation output
- [ ] Reads Image QA output
- [ ] Stops if Image QA is not rejected
- [ ] Produces revised provider prompts
- [ ] Runtime output ignored by Git