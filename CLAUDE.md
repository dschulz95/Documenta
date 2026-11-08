# Project Guidelines

## Project overview

<!-- Short description: what the app does, tech stack, how to run it -->

- Run dev server: `npm run dev`
- Run tests: `npm test`

## Workflow

This project uses OpenSpec for spec-driven development, combined with TDD
and the frontend-design skill.

1. Clarify unclear ideas first (e.g. with /grill-me or /opsx:explore).
2. Create a change with /opsx:propose.
3. Implement it with /opsx:apply.
4. Finish with /opsx:archive and check in the git diff that
   openspec/specs/ was actually updated.

## Proposing changes (/opsx:propose)

- Write tasks as vertical slices that can each be tested on their own.
  Do not create layer-only tasks like "database" or "API".
- If the change touches the UI, use the frontend-design skill to choose a
  visual direction (style, typography, colors, layout, components) and
  record it in design.md under "Visual direction".
- If the project already has a design system or component library,
  follow it instead of inventing a new style.

## Implementing changes (/opsx:apply)

- Work on one task at a time.
- Build behavior (state, validation, interactions, data handling) with the
  tdd skill: write one failing test, write the minimal code to pass it,
  then refactor.
- Derive tests from the scenarios in the change's specs.
- Build styling and layout with the frontend-design skill, following the
  visual direction in design.md.
- Do not write tests for purely visual details like colors or spacing.
- Mark a task as done only when its tests and all existing tests pass.
- If the spec does not match the behavior that is actually needed, stop
  and ask instead of silently deviating from it.
