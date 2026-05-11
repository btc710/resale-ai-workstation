```markdown
# resale-ai-workstation Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the core development patterns, coding conventions, and workflows used in the `resale-ai-workstation` JavaScript codebase. You'll learn how to structure files, write imports/exports, and create and run tests following the repository's established practices. This guide also provides suggested commands for common workflows to streamline your development process.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `userProfile.js`, `orderManager.js`

### Import Style
- Use **relative imports** to reference other modules.
  - Example:
    ```javascript
    import { fetchData } from './apiUtils';
    ```

### Export Style
- Use **named exports** for functions, objects, or constants.
  - Example:
    ```javascript
    // In userProfile.js
    export function getUserProfile(id) {
      // ...
    }
    ```

    ```javascript
    // In another file
    import { getUserProfile } from './userProfile';
    ```

### Commit Patterns
- Commit messages are **freeform** (no strict prefix), with an average length of 46 characters.
  - Example: `fix bug in order calculation logic`

## Workflows

### Adding a New Module
**Trigger:** When you need to add new functionality as a separate module.
**Command:** `/add-module`

1. Create a new file using camelCase naming (e.g., `newFeature.js`).
2. Write your logic using named exports.
    ```javascript
    export function doSomething() {
      // implementation
    }
    ```
3. Import your module where needed using a relative path.
    ```javascript
    import { doSomething } from './newFeature';
    ```
4. Write a corresponding test file named `newFeature.test.js`.

### Writing and Running Tests
**Trigger:** When you add or update code and need to ensure correctness.
**Command:** `/run-tests`

1. Create a test file with the pattern `*.test.js` (e.g., `userProfile.test.js`).
2. Write your test cases using your preferred testing framework (framework is currently unknown).
3. Run tests using the project's test runner (consult project documentation or package.json for the exact command).

### Refactoring Code
**Trigger:** When improving or restructuring existing code.
**Command:** `/refactor`

1. Identify the file(s) to refactor.
2. Apply changes, maintaining camelCase file naming and relative imports.
3. Update any affected imports/exports.
4. Run all relevant tests to ensure nothing is broken.

## Testing Patterns

- Test files follow the pattern `*.test.js` and are placed alongside or near the modules they test.
- The specific testing framework is **unknown**; check the project for details.
- Example test file:
  ```javascript
  // userProfile.test.js
  import { getUserProfile } from './userProfile';

  test('should fetch user profile by ID', () => {
    // test implementation
  });
  ```

## Commands

| Command        | Purpose                                      |
|----------------|----------------------------------------------|
| /add-module    | Scaffold a new module with proper conventions|
| /run-tests     | Run all test files matching `*.test.js`      |
| /refactor      | Start a code refactoring workflow            |
```
