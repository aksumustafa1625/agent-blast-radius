'use strict';

const { Command, Flags } = require('@oclif/core');
const { spawn } = require('node:child_process');
const path = require('node:path');

// Repo root is three levels up from commands/blast-radius/.
const REPO_ROOT = path.join(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'blast_radius', 'cli.py');

class ReportCommand extends Command {
  async run() {
    const { flags } = await this.parse(ReportCommand);

    const args = [CLI, '--agent', flags.agent];
    if (flags['target-org']) args.push('--org', flags['target-org']);
    if (flags['running-user']) args.push('--running-user', flags['running-user']);
    if (flags['permission-set']) args.push('--permission-set', flags['permission-set']);
    if (flags['source-root']) args.push('--source-root', flags['source-root']);
    if (flags['no-retrieve']) args.push('--no-retrieve');
    if (flags.out) args.push('--out', flags.out);

    const python = process.env.BLAST_RADIUS_PYTHON || 'python';

    await new Promise((resolve, reject) => {
      const child = spawn(python, args, { stdio: 'inherit' });
      child.on('error', (err) => reject(new Error(`Could not launch Python ('${python}'): ${err.message}`)));
      child.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`analysis exited with code ${code}`))));
    });
  }
}

ReportCommand.summary = "Compute an Agentforce agent's blast radius.";
ReportCommand.description =
  'Reads the agent config, its Apex/Flow actions, the running user\'s permissions, and the ' +
  'org\'s own GDPR/ComplianceGroup labels - all live via the Salesforce CLI - and writes a ' +
  'deterministic Markdown + HTML report. No agent is invoked; zero Flex Credits. Run from the ' +
  'root of a Salesforce DX project (so force-app is on the path).';

ReportCommand.examples = [
  '<%= config.bin %> blast-radius report --agent HealthRecord_Assistant --permission-set HR_Agent_Minimal',
  '<%= config.bin %> blast-radius report --agent My_Agent --running-user svc@acme.com --target-org acmeOrg',
];

ReportCommand.flags = {
  agent: Flags.string({ char: 'a', required: true, summary: 'GenAiPlannerBundle API name of the agent.' }),
  'target-org': Flags.string({ char: 'o', summary: 'Target org alias or username (default org if omitted).' }),
  'running-user': Flags.string({ char: 'u', summary: 'Username to model as the running user.' }),
  'permission-set': Flags.string({ char: 'p', summary: 'Model the running user as this permission set.' }),
  'source-root': Flags.string({ summary: 'Path to force-app/main/default (default: force-app/main/default).' }),
  'no-retrieve': Flags.boolean({ summary: 'Skip retrieving agent metadata (use what is already local).' }),
  out: Flags.string({ summary: 'Output path prefix for the .md and .html reports.' }),
};

module.exports = ReportCommand;
