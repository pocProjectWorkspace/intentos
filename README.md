# IntentOS
### *Language is the Interface*

---

## The Problem

Every computer user alive today has felt this friction:

You want to **do something simple**. Remove a background from a photo. Extract audio from a video. Find the cheapest flight and book it. Merge two PDFs. Speed up a recording.

But before you can do the thing, you have to **do a hundred other things first.**

Find an app. Download it. Install it. Learn it. Pay for it. Update it. And then — only then — do the actual thing you wanted to do in the first place.

The app was never the point. The app was always in the way.

We built computers that are extraordinary at processing language, image, audio, and data — and then buried all of that power behind menus, icons, and installation wizards. We made people learn the computer instead of making the computer learn the people.

**IntentOS is the correction.**

---

## The Vision

IntentOS is an operating system where **language is the interface**.

Not a layer on top of a traditional OS. Not a chatbot bolted onto Windows or macOS. A ground-up rethinking of what an operating system is for.

In IntentOS, there are no apps to install. There are only **tasks to describe.**

> *"Crop all the photos in this folder to square, boost the contrast, and rename them by date."*

> *"Play the podcast in my downloads folder. Skip any ad breaks."*

> *"Find the invoice from March, extract the total, and add it to my expense spreadsheet."*

> *"What's the fastest route to the airport right now? Book me an Uber for 30 minutes before my flight."*

You describe what you want. IntentOS figures out how to do it. No app required. No learning curve. No installation.

The operating system becomes **an intelligent execution layer** — a substrate that routes your intent to the right agents, assembles the right tools, and returns the result. The complexity lives inside the OS, invisible to the user.

---

## What IntentOS Is

**For everyday users:** A computer that finally works the way you think. You don't need to know what software to use. You don't need to learn new tools. You just need to be able to describe what you want.

**For developers:** A platform where you build *agents and capabilities*, not apps. You contribute a skill — say, audio stem separation or PDF parsing — and IntentOS routes tasks to it automatically. No UI required. No distribution headache. Your capability becomes part of the OS.

**For everyone:** The end of the app economy as a tax on getting things done.

---

## Core Principles

**1. Language is the interface.**
Every interaction with IntentOS is a natural language instruction. No menus. No icons to learn. No modes to switch between. If you can describe it, IntentOS can attempt it.

**2. Intent over application.**
There are no apps in IntentOS. There are capabilities. The difference is that capabilities are invisible — they compose automatically to serve a task, and dissolve when the task is done. You never manage them.

**3. Agents all the way down.**
Under the hood, IntentOS is a multi-agent operating system. Each capability is an agent. The scheduler is an agent. The file system has an agent. They communicate, collaborate, and hand off to each other — orchestrated by a task kernel that the user never sees.

**4. Every person's computer, not every developer's computer.**
IntentOS is built for the person who just wants to get things done. The nurse. The small business owner. The student. The artist. Not just the engineer who knows what a terminal is.

**5. Open and composable.**
IntentOS is open source. Its capability layer is a public registry — anyone can contribute agents, anyone can fork the OS, anyone can build on the substrate. Like Linux, it belongs to everyone.

---

## What IntentOS Replaces

| Traditional OS | IntentOS |
|---|---|
| Install an app to play video | *"Play this video at 1.5x speed"* |
| Open Photoshop to edit an image | *"Remove the background from all product photos in this folder"* |
| Use a browser to search and book | *"Find me a return flight to Dubai under $400 next month"* |
| Open a DAW to edit audio | *"Extract the vocals from this track and save as MP3"* |
| Manage files manually | *"Archive everything I haven't opened in 6 months"* |
| Run terminal commands | *"Free up disk space — keep my recent projects"* |

---

## The Technical Foundation

IntentOS is built on a forked and extended version of the OpenClaw agentic platform, with the following layers:

- **Intent Kernel** — receives natural language tasks, parses intent, routes to agents
- **Agent Scheduler** — manages agent lifecycles, spawns and dissolves capabilities as needed
- **Capability Registry** — a package-like system of agents (file, media, browser, image, system, etc.)
- **Semantic Memory Layer** — persistent context about the user, their files, and their preferences
- **Task Interface** — the single-surface UI: a text input, a task history, and a result pane. Nothing else.
- **Agentic Browser** — a headless browser agent that acts on web tasks without exposing a traditional browser UI
- **ACP (Agent Communication Protocol)** — the standard contract between agents, inherited and extended from OpenClaw

---

## What We're Building First

The first milestone for IntentOS is a working **task shell** — a minimal desktop environment where:

1. You type a task in plain language
2. The intent kernel breaks it into sub-tasks
3. Agents execute each sub-task
4. The result is returned to the screen

No app launcher. No file manager. No settings panel. Just the task shell.

From there, capabilities are added one by one — file agent, browser agent, media agent, image agent — each one making the OS more useful for everyday tasks.

---

## Why Now

The technology to build this has existed for about 18 months. The models are capable enough. The agent frameworks are mature enough. The compute is cheap enough.

What hasn't existed is the will to rethink the OS itself, rather than patch the one we have.

IntentOS is that rethink.

---

## Join the Build

IntentOS is being built in public, by a small team with a sharp vision and no patience for the way things have always been done.

If you're a developer who wants to build agent capabilities, open a PR.
If you're a designer who wants to think about what "no UI" actually looks like, open an issue.
If you're a user who's tired of installing apps to do simple things, star the repo and watch what happens.

**The interface of the future is a sentence.**

---

*IntentOS — Built on OpenClaw. Pointed at something new.*
