# Image Prompt Agent Checklist

## Architecture

- [x] Responsibility defined
- [x] Input contract defined
- [x] Output contract defined
- [x] Provider separation defined
- [x] Schema defined
- [x] QA approval dependency defined

## Implementation

- [ ] output.py
- [ ] prompt.py
- [ ] run.py
- [ ] JSON validation
- [ ] Archive system
- [ ] Production test

## Quality

- [ ] Reads Visual Brief output
- [ ] Reads QA output
- [ ] Stops if QA is not approved
- [ ] Produces OpenAI prompt
- [ ] Produces Flux prompt
- [ ] Produces Midjourney prompt
- [ ] Runtime output ignored by Git