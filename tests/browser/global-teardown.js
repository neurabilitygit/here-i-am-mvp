const {execFileSync} = require('node:child_process');

module.exports = async function globalTeardown() {
  try {
    const output = execFileSync(
      'docker',
      ['ps', '-q', '--filter', 'label=com.hereiam.browser-test=true'],
      {encoding: 'utf8'},
    );
    for (const containerId of output.trim().split(/\s+/).filter(Boolean)) {
      execFileSync('docker', ['stop', containerId], {stdio: 'ignore'});
    }
  } catch (_error) {
    // CI starts uvicorn directly and may not have a Docker daemon. There is
    // nothing to clean up in that execution path.
  }
};
