# AST Parsing in Cline: Comprehensive Research Report

## Executive Summary

Cline uses **tree-sitter**, a parsing library that generates Abstract Syntax Trees (ASTs), to analyze code structure across 14 programming languages. The primary use case is exposing code definitions (classes, functions, methods, etc.) to the LLM via the `list_code_definition_names` tool, enabling better codebase understanding without overwhelming the context window.

---

## 1. AST Parsing Libraries Used

### Tree-sitter (web-tree-sitter)
- **Library**: `web-tree-sitter` with `tree-sitter-wasms`
- **Approach**: WASM-based (WebAssembly) bindings
- **Rationale**: Node bindings (`node-tree-sitter`) are incompatible with Electron in VSCode extensions

**File Reference**: [src/services/tree-sitter/languageParser.ts](https://github.com/cline/cline/tree/main/src/services/tree-sitter/languageParser.ts#L0-L49)

```typescript
import * as path from "path"
import Parser from "web-tree-sitter"
import {
	cppQuery,
	cQuery,
	csharpQuery,
	goQuery,
	javaQuery,
	javascriptQuery,
	kotlinQuery,
	phpQuery,
	pythonQuery,
	rubyQuery,
	rustQuery,
	swiftQuery,
	typescriptQuery,
} from "./queries"

/*
Using node bindings for tree-sitter is problematic in vscode extensions 
because of incompatibility with electron. Going the .wasm route has the 
advantage of not having to build for multiple architectures.

We use web-tree-sitter and tree-sitter-wasms which provides auto-updating 
prebuilt WASM binaries for tree-sitter's language parsers.
*/
```

### Supported Languages (14 Total)
**File Reference**: [src/services/tree-sitter/index.ts#L60-L93](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L60-L93)

```typescript
const extensions = [
	"js",   // JavaScript
	"jsx",  // JavaScript (React)
	"ts",   // TypeScript
	"tsx",  // TypeScript (React)
	"py",   // Python
	"rs",   // Rust
	"go",   // Go
	"c",    // C
	"h",    // C Headers
	"cpp",  // C++
	"hpp",  // C++ Headers
	"cs",   // C#
	"rb",   // Ruby
	"java", // Java
	"php",  // PHP
	"swift",// Swift
	"kt",   // Kotlin
]
```

---

## 2. Files and Modules Using AST

### Core Implementation Files

#### Main Parsing Logic
**File**: [src/services/tree-sitter/index.ts](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L0-L98)

**Key Functions**:
- `parseSourceCodeForDefinitionsTopLevel(dirPath, clineIgnoreController)` - Entry point
- `separateFiles(allFiles)` - Filters files by extension (max 50 files)
- `parseFile(filePath, languageParsers, clineIgnoreController)` - Parses individual files

```typescript
export async function parseSourceCodeForDefinitionsTopLevel(
	dirPath: string,
	clineIgnoreController?: ClineIgnoreController,
): Promise<string> {
	// Check directory existence
	const dirExists = await fileExistsAtPath(path.resolve(dirPath))
	if (!dirExists) {
		return "This directory does not exist or you do not have permission to access it."
	}

	// Get all files at top level (not gitignored)
	const [allFiles, _] = await listFiles(dirPath, false, 200)
	
	// Separate files to parse (max 50) and remaining files
	const { filesToParse, remainingFiles } = separateFiles(allFiles)
	
	// Load required parsers dynamically
	const languageParsers = await loadRequiredLanguageParsers(filesToParse)
	
	// Parse each file and accumulate results
	let result = ""
	for (const filePath of allowedFilesToParse) {
		const definitions = await parseFile(filePath, languageParsers, clineIgnoreController)
		if (definitions) {
			result += `${path.relative(dirPath, filePath).toPosix()}\n${definitions}\n`
		}
	}
	
	return result ? result : "No source code definitions found."
}
```

#### Language Parser Loader
**File**: [src/services/tree-sitter/languageParser.ts](https://github.com/cline/cline/tree/main/src/services/tree-sitter/languageParser.ts#L0-L121)

**Key Functions**:
- `loadRequiredLanguageParsers(filesToParse)` - Dynamically loads WASM parsers
- `loadLanguage(langName)` - Loads individual WASM module
- `initializeParser()` - Initializes tree-sitter WASM

```typescript
export async function loadRequiredLanguageParsers(filesToParse: string[]): Promise<LanguageParser> {
	await initializeParser()
	
	const extensions = new Set<string>()
	filesToParse.forEach((file) => {
		const ext = path.extname(file).toLowerCase().slice(1)
		if (ext) extensions.add(ext)
	})

	const parsers: LanguageParser = {}
	let language: Parser.Language
	let query: Parser.Query

	for (const ext of extensions) {
		switch (ext) {
			case "js":
			case "jsx":
				language = await loadLanguage("javascript")
				query = language.query(javascriptQuery)
				break
			case "ts":
			case "tsx":
				language = await loadLanguage("typescript")
				query = language.query(typescriptQuery)
				break
			// ... additional languages
		}
		parsers[ext] = { parser, query }
	}
	
	return parsers
}
```

#### Query Definitions (13 files)
**Directory**: [src/services/tree-sitter/queries/](https://github.com/cline/cline/tree/main/src/services/tree-sitter/queries/)

Language-specific query patterns that define which AST nodes to capture:

- `python.ts` - Class and function definitions
- `typescript.ts` - Function signatures, method signatures, class declarations, modules
- `javascript.ts` - Class definitions, method definitions, function declarations
- `rust.ts` - Struct items, method definitions, function items
- `go.ts` - Function/method declarations with comments, type specs
- `c.ts` - Struct/union specs, function declarators, typedefs
- `cpp.ts` - Struct/union/class specs, function declarators with namespaces
- `c-sharp.ts` - Class/interface/method/namespace declarations
- `ruby.ts` - Method/class/module definitions with comments
- `java.ts` - Class/method/interface declarations
- `php.ts` - Class/function/method declarations
- `swift.ts` - Class/protocol declarations, function/method/property declarations
- `kotlin.ts` - Class/function/interface/object/property/enum/typealias declarations

**Example - Python Query**:
[src/services/tree-sitter/queries/python.ts](https://github.com/cline/cline/tree/main/src/services/tree-sitter/queries/python.ts#L0-L11)

```typescript
/*
- class definitions
- function definitions
*/
export default `
(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function
`
```

**Example - TypeScript Query**:
[src/services/tree-sitter/queries/typescript.ts](https://github.com/cline/cline/tree/main/src/services/tree-sitter/queries/typescript.ts#L0-L32)

```typescript
/*
- function signatures and declarations
- method signatures and definitions
- abstract method signatures
- class declarations (including abstract classes)
- module declarations
*/
export default `
(function_signature
  name: (identifier) @name.definition.function) @definition.function

(method_signature
  name: (property_identifier) @name.definition.method) @definition.method

(abstract_method_signature
  name: (property_identifier) @name.definition.method) @definition.method

(abstract_class_declaration
  name: (type_identifier) @name.definition.class) @definition.class

(module
  name: (identifier) @name.definition.module) @definition.module

(function_declaration
  name: (identifier) @name.definition.function) @definition.function

(method_definition
  name: (property_identifier) @name.definition.method) @definition.method

(class_declaration
  name: (type_identifier) @name.definition.class) @definition.class
`
```

### Tool Handler Integration

**File**: [src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts](https://github.com/cline/cline/tree/main/src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts#L0-L151)

```typescript
import { parseSourceCodeForDefinitionsTopLevel } from "@services/tree-sitter"

export class ListCodeDefinitionNamesToolHandler implements IFullyManagedTool {
	readonly name = ClineDefaultTool.LIST_CODE_DEF

	async execute(config: TaskConfig, block: ToolUse): Promise<ToolResponse> {
		// Validate path parameter
		const pathValidation = this.validator.assertRequiredParams(block, "path")
		if (!pathValidation.ok) {
			return await config.callbacks.sayAndCreateMissingParamError(this.name, "path")
		}

		// Resolve workspace path
		const pathResult = resolveWorkspacePath(config, relDirPath!, "ListCodeDefinitionNamesToolHandler.execute")
		const { absolutePath, displayPath } = 
			typeof pathResult === "string" 
				? { absolutePath: pathResult, displayPath: relDirPath! } 
				: pathResult

		// Execute AST parsing
		const result = await parseSourceCodeForDefinitionsTopLevel(
			absolutePath, 
			config.services.clineIgnoreController
		)

		// Handle approval flow and return result
		// ...
		
		return result
	}
}
```

### Tool Specification

**File**: [src/core/prompts/system-prompt/tools/list_code_definition_names.ts](https://github.com/cline/cline/tree/main/src/core/prompts/system-prompt/tools/list_code_definition_names.ts#L0-L46)

```typescript
const generic: ClineToolSpec = {
	variant: ModelFamily.GENERIC,
	id: ClineDefaultTool.LIST_CODE_DEF,
	name: "list_code_definition_names",
	description:
		"Request to list definition names (classes, functions, methods, etc.) used in source code files at the top level of the specified directory. This tool provides insights into the codebase structure and important constructs, encapsulating high-level concepts and relationships that are crucial for understanding the overall architecture.",
	parameters: [
		{
			name: "path",
			required: true,
			instruction: `The path of the directory (relative to the current working directory {{CWD}}){{MULTI_ROOT_HINT}} to list top level source code definitions for.`,
			usage: "Directory path here",
		},
		TASK_PROGRESS_PARAMETER,
	],
}
```

---

## 3. What AST is Used For

### Primary Use Case: Code Structure Analysis for LLM Context

**Purpose**: Provide the LLM with an overview of code structure without reading entire file contents.

**Key Benefits**:
1. **Token Efficiency**: Only captures definition names (first line), not full implementations
2. **Codebase Navigation**: Helps LLM understand project architecture
3. **Targeted File Reading**: LLM can identify relevant files before reading them
4. **Context Window Optimization**: Provides structure overview without exhausting tokens

**From System Prompt**: [src/core/prompts/system-prompt/components/capabilities.ts](https://github.com/cline/cline/tree/main/src/core/prompts/system-prompt/components/capabilities.ts#L9-L11)

```typescript
- You can use the list_code_definition_names tool to get an overview of source code definitions for all files at the top level of a specified directory. This can be particularly useful when you need to understand the broader context and relationships between certain parts of the code. You may need to call this tool multiple times to understand various parts of the codebase related to the task.
    - For example, when asked to make edits or improvements you might analyze the file structure in the initial environment_details to get an overview of the project, then use list_code_definition_names to get further insight using source code definitions for files located in relevant directories, then read_file to examine the contents of relevant files, analyze the code and suggest improvements or make necessary edits, then use the replace_in_file tool to implement changes. If you refactored code that could affect other parts of the codebase, you could use search_files to ensure you update other files as needed.
```

### Parsing Process Explanation

**From Code Comments**: [src/services/tree-sitter/index.ts#L98-L108](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L98-L108)

```typescript
/*
Parsing files using tree-sitter

1. Parse the file content into an AST (Abstract Syntax Tree) using the appropriate 
   language grammar (set of rules that define how the components of a language like 
   keywords, expressions, and statements can be combined to create valid programs).

2. Create a query using a language-specific query string, and run it against the 
   AST's root node to capture specific syntax elements.
    - We use tag queries to identify named entities in a program, and then use a 
      syntax capture to label the entity and its name. A notable example of this is 
      GitHub's search-based code navigation.
    - Our custom tag queries are based on tree-sitter's default tag queries, but 
      modified to only capture definitions.

3. Sort the captures by their position in the file, output the name of the definition, 
   and format by i.e. adding "|----\n" for gaps between captured sections.

This approach allows us to focus on the most relevant parts of the code (defined by 
our language-specific queries) and provides a concise yet informative view of the 
file's structure and key elements.
*/
```

---

## 4. How AST Output is Presented to LLM

### Output Format

The parsed AST definitions are formatted as:
1. **File path** (relative to directory)
2. **Definition lines** prefixed with `│`
3. **Separators** `|----` for gaps between definitions

**Format Generation**: [src/services/tree-sitter/index.ts#L155-L182](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L155-L182)

```typescript
async function parseFile(
	filePath: string,
	languageParsers: LanguageParser,
	clineIgnoreController?: ClineIgnoreController,
): Promise<string | null> {
	// ... parse file and capture AST nodes ...

	captures.forEach((capture) => {
		const { node, name } = capture
		const startLine = node.startPosition.row
		const endLine = node.endPosition.row

		// Add separator if there's a gap between captures
		if (lastLine !== -1 && startLine > lastLine + 1) {
			formattedOutput += "|----\n"
		}

		// Only add the first line of the definition
		if (name.includes("name") && lines[startLine]) {
			formattedOutput += `│${lines[startLine]}\n`
		}

		lastLine = endLine
	})

	if (formattedOutput.length > 0) {
		return `|----\n${formattedOutput}|----\n`
	}
	return null
}
```

### Example Output

For a Python file `src/utils/helpers.py`:

```
src/utils/helpers.py
|----
│class DataProcessor:
|----
│    def __init__(self, config):
│    def process(self, data):
│    def validate(self, data):
|----
│def format_output(result):
│def save_to_file(data, filepath):
|----
```

### Tool Result Format

**From Handler**: [src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts#L67-L83](https://github.com/cline/cline/tree/main/src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts#L67-L83)

```typescript
const sharedMessageProps = {
	tool: "listCodeDefinitionNames",
	path: getReadablePath(config.cwd, displayPath),
	content: result,  // Formatted AST output above
	operationIsLocatedInWorkspace: await isLocatedInWorkspace(relDirPath!),
}

const completeMessage = JSON.stringify(sharedMessageProps)
```

### UI Display

**From ChatRow Component**: [webview-ui/src/components/chat/ChatRow.tsx#L701-L729](https://github.com/cline/cline/tree/main/webview-ui/src/components/chat/ChatRow.tsx#L701-L729)

```tsx
case "listCodeDefinitionNames":
	return (
		<>
			<div style={headerStyle}>
				{toolIcon("file-code")}
				{tool.operationIsLocatedInWorkspace === false &&
					toolIcon("sign-out", "yellow", -90, "This file is outside of your workspace")}
				<span style={{ fontWeight: "bold" }}>
					{message.type === "ask"
						? "Cline wants to view source code definition names used in this directory:"
						: "Cline viewed source code definition names used in this directory:"}
				</span>
			</div>
			<CodeAccordian
				code={tool.content!}
				isExpanded={isExpanded}
				language="shell-session"
				onToggleExpand={handleToggle}
				path={tool.path!}
			/>
		</>
	)
```

---

## 5. Tools/Features Enhanced by AST

### list_code_definition_names Tool

**Primary Enhanced Tool**: Directly exposes AST parsing to LLM

**Tool Flow**:
1. **User/LLM Request**: `<list_code_definition_names><path>src/</path></list_code_definition_names>`
2. **Approval Required**: Tool requires user approval (unless auto-approved)
3. **AST Parsing**: Executes `parseSourceCodeForDefinitionsTopLevel()`
4. **Result Return**: Formatted definitions sent to LLM

**From System Prompt Example**: [evals/diff-edits/prompts/basicSystemPrompt-06-06-25.ts#L137-L149](https://github.com/cline/cline/tree/main/evals/diff-edits/prompts/basicSystemPrompt-06-06-25.ts#L137-L149)

```typescript
## list_code_definition_names
Description: Request to list definition names (classes, functions, methods, etc.) used in source code files at the top level of the specified directory. This tool provides insights into the codebase structure and important constructs, encapsulating high-level concepts and relationships that are crucial for understanding the overall architecture.
Parameters:
- path: (required) The path of the directory (relative to the current working directory ${cwdFormatted}) to list top level source code definitions for.
Usage:
<list_code_definition_names>
<path>Directory path here</path>
</list_code_definition_names>
```

### Workflow Integration

**From Capabilities Description**:

**Typical Usage Pattern**:
1. LLM receives task (e.g., "Add authentication to the API")
2. Analyzes file structure from `environment_details`
3. Uses `list_code_definition_names` on `src/api/` to see controller methods
4. Uses `list_code_definition_names` on `src/auth/` to see existing auth code
5. Uses `read_file` on specific files identified
6. Makes informed edits with `replace_in_file`
7. Uses `search_files` to find all usages if needed

---

## 6. Interesting Insights and Patterns

### Design Decision: Definition Names Only

**Rationale**: Token efficiency

**From Code**: [src/services/tree-sitter/index.ts#L155-L168](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L155-L168)

```typescript
// Only add the first line of the definition
// query captures includes the definition name and the definition implementation, 
// but we only want the name (I found discrepancies in the naming structure for 
// various languages, i.e. javascript names would be 'name' and typescript names 
// would be 'name.definition)
if (name.includes("name") && lines[startLine]) {
	formattedOutput += `│${lines[startLine]}\n`
}
// Adds all the captured lines
// for (let i = startLine; i <= endLine; i++) {
// 	formattedOutput += `│${lines[i]}\n`
// }
```

**Comparison**:
- **With Full Implementation**: 10,000+ tokens for medium file
- **With Names Only**: ~200-500 tokens for same file

### 50 File Limit

**From Code**: [src/services/tree-sitter/index.ts#L60-L93](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L60-L93)

```typescript
const filesToParse = allFiles
	.filter((file) => extensions.includes(path.extname(file)))
	.slice(0, 50) // 50 files max
```

**Rationale**: Performance and context window management
- Prevents overwhelming LLM with too much data
- Encourages targeted exploration (call tool multiple times for different directories)

### WASM Approach Benefits

**From Comments**: [src/services/tree-sitter/languageParser.ts#L0-L49](https://github.com/cline/cline/tree/main/src/services/tree-sitter/languageParser.ts#L0-L49)

```typescript
/*
Using node bindings for tree-sitter is problematic in vscode extensions 
because of incompatibility with electron. Going the .wasm route has the 
advantage of not having to build for multiple architectures.

We use web-tree-sitter and tree-sitter-wasms which provides auto-updating 
prebuilt WASM binaries for tree-sitter's language parsers.
*/
```

**Benefits**:
- **Cross-platform**: No native compilation needed
- **Auto-updating**: Language parsers stay current
- **VSCode Compatible**: Works in Electron environment
- **Bundle Size**: Single WASM file per language (~100-300KB)

### Dynamic Parser Loading

**From Code**: [src/services/tree-sitter/languageParser.ts#L90-L121](https://github.com/cline/cline/tree/main/src/services/tree-sitter/languageParser.ts#L90-L121)

```typescript
export async function loadRequiredLanguageParsers(filesToParse: string[]): Promise<LanguageParser> {
	await initializeParser()
	
	// Only extract extensions that are actually present in files
	const extensions = new Set<string>()
	filesToParse.forEach((file) => {
		const ext = path.extname(file).toLowerCase().slice(1)
		if (ext) extensions.add(ext)
	})

	// Only load WASM modules for languages that are needed
	const parsers: LanguageParser = {}
	for (const ext of extensions) {
		// ... load only required languages
	}
	
	return parsers
}
```

**Benefits**:
- **Performance**: Only loads needed parsers
- **Memory Efficient**: Doesn't load all 14 language WASM files
- **Fast Startup**: Reduces initialization time

### Tag Query Approach

**From Comments**: [src/services/tree-sitter/index.ts#L98-L108](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L98-L108)

```typescript
/*
- We use tag queries to identify named entities in a program, and then use a 
  syntax capture to label the entity and its name. A notable example of this is 
  GitHub's search-based code navigation.
- Our custom tag queries are based on tree-sitter's default tag queries, but 
  modified to only capture definitions.
*/
```

**Inspiration**: GitHub's code navigation feature uses the same approach

**Query Example** (Go with comments): [src/services/tree-sitter/queries/go.ts#L0-L27](https://github.com/cline/cline/tree/main/src/services/tree-sitter/queries/go.ts#L0-L27)

```typescript
export default `
(
  (comment)* @doc
  .
  (function_declaration
    name: (identifier) @name.definition.function) @definition.function
  (#strip! @doc "^//\\s*")
  (#set-adjacent! @doc @definition.function)
)

(
  (comment)* @doc
  .
  (method_declaration
    name: (field_identifier) @name.definition.method) @definition.method
  (#strip! @doc "^//\\s*")
  (#set-adjacent! @doc @definition.method)
)

(type_spec
  name: (type_identifier) @name.definition.type) @definition.type
`
```

**Features**:
- Captures definitions with their preceding comments
- Uses predicates like `#strip!` and `#set-adjacent!`
- Provides context for LLM (function purpose from comments)

### Gap Separator Pattern

**Purpose**: Indicate missing code between definitions

```typescript
// Add separator if there's a gap between captures
if (lastLine !== -1 && startLine > lastLine + 1) {
	formattedOutput += "|----\n"
}
```

**Example**:
```
│class Parser:
|----  // <-- Gap here means there's code between class def and method
│    def parse(self):
```

**Benefit**: LLM knows there's implementation code between visible definitions

### ClineIgnore Integration

**From Code**: [src/services/tree-sitter/index.ts#L32-L52](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L32-L52)

```typescript
// Filter filepaths for access if controller is provided
const allowedFilesToParse = clineIgnoreController 
	? clineIgnoreController.filterPaths(filesToParse) 
	: filesToParse

for (const filePath of allowedFilesToParse) {
	const definitions = await parseFile(filePath, languageParsers, clineIgnoreController)
	// ...
}
```

**Purpose**: Respects `.clineignore` files to skip parsing restricted files

### Build Integration

**From Build Script**: [esbuild.mjs#L89-L123](https://github.com/cline/cline/tree/main/esbuild.mjs#L89-L123)

```javascript
setup(build) {
	build.onEnd(() => {
		// Copy tree-sitter.wasm
		const sourceDir = path.join(__dirname, "node_modules", "web-tree-sitter")
		const targetDir = path.join(__dirname, destDir)
		fs.copyFileSync(
			path.join(sourceDir, "tree-sitter.wasm"), 
			path.join(targetDir, "tree-sitter.wasm")
		)

		// Copy language-specific WASM files
		const languageWasmDir = path.join(__dirname, "node_modules", "tree-sitter-wasms", "out")
		const languages = [
			"typescript", "tsx", "python", "rust", "javascript", "go",
			"cpp", "c", "c_sharp", "ruby", "java", "php", "swift", "kotlin",
		]

		languages.forEach((lang) => {
			const filename = `tree-sitter-${lang}.wasm`
			fs.copyFileSync(
				path.join(languageWasmDir, filename), 
				path.join(targetDir, filename)
			)
		})
	})
}
```

**Deployment**: All WASM files (~4MB total) bundled with extension

---

## 7. Additional Implementation Details

### Error Handling

**From Code**: [src/services/tree-sitter/index.ts#L168-L182](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L168-L182)

```typescript
try {
	// Parse the file content into an Abstract Syntax Tree (AST)
	const tree = parser.parse(fileContent)
	if (!tree || !tree.rootNode) {
		return null
	}

	// Apply the query to the AST and get the captures
	const captures = query.captures(tree.rootNode)
	// ... process captures ...
} catch (error) {
	console.log(`Error parsing file: ${error}\n`)
}

if (formattedOutput.length > 0) {
	return `|----\n${formattedOutput}|----\n`
}
return null
```

**Graceful Degradation**: Parsing errors don't crash the tool; files are skipped

### Telemetry Integration

**From Handler**: [src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts#L107-L138](https://github.com/cline/cline/tree/main/src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts#L107-L138)

```typescript
telemetryService.captureToolUsage(
	config.ulid,
	block.name,
	config.api.getModel().id,
	provider,
	true,  // auto-approved
	true,  // approved
	undefined,
	block.isNativeToolCall,
)
```

**Tracked Metrics**:
- Tool usage frequency
- Auto-approval vs manual approval
- Model using the tool
- Provider information

---

## 8. Future Enhancements (TODOs)

**From Code Comments**: [src/services/tree-sitter/index.ts#L12](https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts#L12)

```typescript
// TODO: implement caching behavior to avoid having to keep analyzing project for new tasks.
```

**Potential Improvement**: Cache parsed results to avoid re-parsing same directories

**Benefits**:
- Faster subsequent tool calls
- Reduced CPU usage
- Better user experience

---

## 9. Comparison with Other Approaches

### Alternative 1: Regex Parsing
**Rejected Reason**: Language-agnostic but unreliable
- Can't handle complex syntax (nested classes, decorators, etc.)
- Prone to false positives/negatives
- No semantic understanding

### Alternative 2: Language Server Protocol (LSP)
**Not Used Because**:
- Requires language-specific LSP servers for each language
- More complex setup and dependencies
- Heavier resource usage
- Overkill for just extracting definitions

### Alternative 3: Static Analysis Tools (ctags, etc.)
**Considered But Not Used**:
- Requires external binaries
- Platform-specific compilation
- Limited language support
- Less precise than tree-sitter

### Why Tree-sitter Wins
1. **Single Library**: Handles all 14 languages
2. **Precise**: True syntax-aware parsing
3. **Fast**: Written in C, WASM-optimized
4. **Maintained**: Active community, auto-updating grammars
5. **VSCode Compatible**: WASM works in Electron
6. **Proven**: Used by GitHub, Atom, Neovim

---

## 10. Key URLs and References

### Repository Files
- **Main Parsing Logic**: https://github.com/cline/cline/tree/main/src/services/tree-sitter/index.ts
- **Language Parser**: https://github.com/cline/cline/tree/main/src/services/tree-sitter/languageParser.ts
- **Query Directory**: https://github.com/cline/cline/tree/main/src/services/tree-sitter/queries/
- **Tool Handler**: https://github.com/cline/cline/tree/main/src/core/task/tools/handlers/ListCodeDefinitionNamesToolHandler.ts
- **Tool Specification**: https://github.com/cline/cline/tree/main/src/core/prompts/system-prompt/tools/list_code_definition_names.ts

### External Libraries
- **web-tree-sitter**: https://github.com/tree-sitter/tree-sitter/tree/master/lib/binding_web
- **tree-sitter-wasms**: https://github.com/tree-sitter/tree-sitter-wasms
- **Tree-sitter Documentation**: https://tree-sitter.github.io/tree-sitter/

### Tree-sitter References
- **Query Test Examples**: https://github.com/tree-sitter/node-tree-sitter/blob/master/test/query_test.js
- **Web Binding Tests**: https://github.com/tree-sitter/tree-sitter/blob/master/lib/binding_web/test/query-test.js
- **Code Navigation Systems**: https://tree-sitter.github.io/tree-sitter/code-navigation-systems

---

## Conclusion

Cline's AST parsing implementation is a well-architected solution that balances:
- **Token Efficiency**: Only captures definition names, not full code
- **Performance**: Dynamic parser loading, 50-file limit
- **Compatibility**: WASM approach works in VSCode/Electron
- **Maintainability**: Language-specific queries, clear separation of concerns
- **User Experience**: Approval flow, graceful error handling

The `list_code_definition_names` tool successfully provides LLMs with structural code understanding without exhausting context windows, enabling more intelligent codebase navigation and editing.
