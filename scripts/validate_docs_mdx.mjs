// Run with a task-local MDX package; no global install or arbitrary shell evaluation.
import {createRequire} from 'node:module';
import {readFile, readdir} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root = path.resolve('docs');
const require = createRequire(path.resolve(process.env.QITOS_DOCS_TOOLS || '.', 'package.json'));
const {compile} = await import(pathToFileURL(require.resolve('@mdx-js/mdx')));
let count = 0, failures = 0;
async function visit(directory) {
  for (const entry of await readdir(directory, {withFileTypes:true})) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory() && !entry.name.startsWith('.')) await visit(file);
    else if (entry.isFile() && file.endsWith('.mdx')) {
      count++;
      try { await compile(await readFile(file, 'utf8')); }
      catch(error) { failures++; process.stderr.write(`${path.relative(root,file)}:${error.line}:${error.column} ${error.reason}\n`); }
    }
  }
}
await visit(root);
console.log(`MDX: ${count} public pages; ${failures} failures`);
process.exitCode = failures ? 1 : 0;
