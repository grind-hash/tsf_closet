# Reference Refresh Guide

This guide is used to regenerate the navigator reference files when they become outdated.

## When to Refresh

- Major refactoring (file renames, directory restructuring)
- Multiple new features have been added since last verification
- "Last verified" dates in reference files are more than 2 weeks old
- An agent reports that a referenced file path doesn't exist

## Refresh Procedure

### Quick Validation (recommended: after each structural change)

After adding/removing/renaming files, update only the affected reference:

1. **New/removed backend route or service** → Edit `references/backend-map.md`
2. **New/removed frontend component, context, or hook** → Edit `references/frontend-map.md`
3. **New data flow pattern** → Edit `references/data-flow.md`
4. **New modification recipe discovered** → Edit `references/modification-recipes.md`

Update the `Last verified` date at the top of the edited file.

### Full Regeneration (when references feel broadly outdated)

Use the Explore subagent with the following prompts to regenerate each reference:

#### Backend Map

```
Explore the backend architecture at backend/gateway/. Report:
1. All routes in routes/*.py with HTTP method, path, and purpose
2. All services (class name + public methods + 1-line purpose)
3. All DB models with key fields
4. All constant definitions
Format as a markdown reference table. Base path: c:\source\tech_study2026\tsf_closet_base\
```

#### Frontend Map

```
Explore the frontend at frontend/src/. Report:
1. App.tsx routing structure
2. All Context providers: state fields + action types
3. All custom hooks: name + purpose
4. All API modules: exported functions + endpoints
5. Component tree (file names + 1-line purpose)
6. Type definitions from types/index.ts (name + key fields)
Base path: c:\source\tech_study2026\tsf_closet_base\
```

#### Data Flow

```
Trace the main game loop data flow in tsf_closet_base:
1. How does a user instruction flow from ChatInput → SSE → backend → image gen → frontend update?
2. What SSE events exist and what do they trigger?
3. Session lifecycle (create → play → end)
Base path: c:\source\tech_study2026\tsf_closet_base\
```

After regeneration, update all `Last verified` dates.

## Self-Maintenance Checklist

When you complete a modification task using this skill, ask yourself:

- [ ] Did I add a new file that should appear in backend-map or frontend-map?
- [ ] Did I create a new route, context, hook, or component?
- [ ] Did I introduce a new data flow pattern?
- [ ] Did I discover a useful modification recipe that isn't documented?

If any answer is yes, update the reference before completing the task.
