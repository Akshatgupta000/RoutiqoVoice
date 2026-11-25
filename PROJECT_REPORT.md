# Routiqo AI Sales Agent

**Candidate:** Akshat Gupta  
**Project:** Fortivex AI technical project challenge  
**Type:** Local demonstration prototype

## Business problem

Routiqo helps logistics companies run delivery centers, vehicles, orders, dispatch, and optimized routes. A first sales conversation still has to be done by a person: explain the product, learn the fleet size and the operational problem, and decide whether a demonstration is worth arranging. Those notes are easy to lose, and the qualification decision is hard to explain if it lives only in someone's memory.

## Proposed solution

A browser sales desk conducts that first conversation. The customer speaks or types. The browser's Web Speech API converts speech to text and later speaks the reply. A FastAPI service answers from a written Routiqo knowledge file, remembers the recent turns the browser sends, scores the lead with visible rules, stores the lead in SQLite, and writes a short call summary with a recommended next step.

A demo request is saved as interest. The application does not claim a calendar booking. If Gemini is unavailable, labeled demo replies keep the same save-and-score path working.

## Key features

- Browser speech recognition and speech output, plus a text box.
- One sales assistant with short replies and a single follow-up question.
- Keyword retrieval over product notes. Not embeddings.
- Lead score out of 100: vehicles, problem, demo interest, and email.
- Status: Qualified, Potential, or Not Qualified, with a next action for the sales team.
- Saved leads table that survives an application restart.
- Call summary from Gemini, or a local template if that call fails.
- Clear demo-mode banner when the reply did not come from Gemini.

## Technology stack

HTML, CSS, and vanilla JavaScript on the page. Python, FastAPI, Pydantic, and Uvicorn on the server. Browser `SpeechRecognition` / `webkitSpeechRecognition` for speech-to-text. Optional Google Gemini through `google-genai`, with the model id in `GEMINI_MODEL`. SQLite for leads. pytest for the scoring, database, and API checks. No React, and no agent framework.

## System workflow

The customer speaks. The browser accumulates finalized speech separately from temporary interim results, then posts the complete finalized transcript with recent messages to `/api/chat` when listening stops. The server selects knowledge sections by word overlap, calls Gemini or builds a demo reply, and returns the text. The browser speaks it. The operator confirms the lead form and saves. The server scores the lead, stores one row, and shows the summary, status, and next action.

## Scalability

The running system is one process and one SQLite file, which is appropriate for a single-user demo. A production version would add a load balancer, several API instances, PostgreSQL, Redis for short-lived call state, background workers for summaries, a real telephony stack for phone calls, monitoring, and rate limits. One hundred thousand registered users are stored accounts. One hundred thousand simultaneous voice calls are live sessions. This prototype does not serve either load.

## Security

The Gemini key stays in `.env` and is not written to the database or API responses. Queries are parameterized. Inputs are validated. The app sends only finalized recognized text to its backend. Browser speech recognition may use browser-provided services; Brave support is not guaranteed. There is no authentication, because the demo is local. A public deployment would need sign-in, HTTPS, secret storage, authorization, rate limits, and a retention policy before customer data is collected.

## Future enhancements

Real calendar booking, CRM export, telephony, stronger search if the knowledge file grows, and authentication before any deployment beyond the laptop.
