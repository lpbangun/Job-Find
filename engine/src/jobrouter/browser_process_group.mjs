// Keep Playwright's Chromium descendants in the supervisor's POSIX process group.
// Playwright normally requests detached:true. We own this isolated worker and
// forbid that escape before loading Playwright; no browser sandbox flag changes.
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
const spawn = childProcess.spawn;
childProcess.spawn = function(command, args, options) {
  if (Array.isArray(args)) return spawn.call(this, command, args, {...options, detached: false});
  return spawn.call(this, command, {...args, detached: false});
};
syncBuiltinESMExports();
