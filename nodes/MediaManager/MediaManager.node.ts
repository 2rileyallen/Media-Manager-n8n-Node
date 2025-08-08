import {
	IExecuteFunctions,
	INodeType,
	INodeTypeDescription,
	ILoadOptionsFunctions,
	INodeExecutionData,
	NodeOperationError,
	INodePropertyOptions,
	INodeProperties,
	NodeConnectionType,
} from 'n8n-workflow';

import { promisify } from 'util';
import { exec } from 'child_process';
import * as path from 'path';

const execAsync = promisify(exec);

/**
 * A helper function to safely extract an error message from an unknown error type.
 * @param error The error object, which is of type 'unknown'.
 * @returns A string representing the error message.
 */
function getErrorMessage(error: unknown): string {
	if (error instanceof Error) {
		const execError = error as Error & { stderr?: string };
		return execError.stderr || execError.message;
	}
	if (typeof error === 'object' && error !== null && 'message' in error && typeof (error as any).message === 'string') {
		return (error as any).message;
	}
	return String(error);
}


/**
 * Executes a command for the manager.py script and handles parsing.
 * This function now automatically detects all required paths.
 * @param command The command to run (e.g., 'list', 'update')
 */
async function executeManagerCommand(
	this: IExecuteFunctions | ILoadOptionsFunctions,
	command: string,
): Promise<any> {
	// --- Fully Automatic Path Detection ---
	const currentNodeDir = __dirname;
	const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');
	const projectPath = path.join(nodeProjectRoot, '..', 'media_manager');
	const managerPath = path.join(projectPath, 'manager.py');
	const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
	const venvSubfolder = process.platform === 'win32' ? 'Scripts' : 'bin';
	const pythonPath = path.join(projectPath, 'venv', venvSubfolder, pythonExecutable);
	// --- End of Automatic Path Detection ---

	const fullCommand = `"${pythonPath}" "${managerPath}" ${command}`;

	try {
		const { stdout, stderr } = await execAsync(fullCommand, { encoding: 'utf-8' });
		if (stderr) {
			console.error(`Manager stderr: ${stderr}`);
		}
		return JSON.parse(stdout);
	} catch (error) {
		console.error(`Error executing command: ${fullCommand}`, error);
		throw new NodeOperationError(this.getNode(), `Failed to execute manager.py command: ${command}. Raw Error: ${getErrorMessage(error)}`);
	}
}


export class MediaManager implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Media Manager',
		name: 'mediaManager',
		icon: 'fa:cogs',
		group: ['transform'],
		version: 1,
		description: 'Dynamically runs Python subcommands from the media-manager project.',
		defaults: {
			name: 'Media Manager',
		},
		inputs: [NodeConnectionType.Main],
		outputs: [NodeConnectionType.Main],
		properties: [
			// --- All path inputs have been removed for a zero-config experience ---

			// --- Refresh Button ---
			// This is now a boolean (toggle switch) that acts as a refresh trigger.
			{
				displayName: 'Refresh Subcommand List',
				name: 'refreshButton',
				type: 'boolean',
				default: false,
				description: 'Toggle this switch to re-scan the subcommands folder for any new or deleted tools.',
			},

			// --- Subcommand Selection Dropdown ---
			{
				displayName: 'Subcommand',
				name: 'subcommand',
				type: 'options',
				typeOptions: {
					loadOptionsMethod: 'getSubcommands',
					loadOptionsDependsOn: ['refreshButton'],
				},
				default: '',
				required: true,
				description: 'Choose the subcommand to run.',
			},

			// --- Dynamic Parameter Section ---
			// This collection will now be dynamically populated with the correct UI fields.
			{
				displayName: 'Parameters',
				name: 'parameters',
				placeholder: 'Add Parameter',
				type: 'collection',
				default: {},
				typeOptions: {
					loadOptionsMethod: 'getSubcommandParameters',
					loadOptionsDependsOn: ['subcommand'],
				},
			},
		],
	};

	methods = {
		loadOptions: {
			// This method is triggered by the 'refreshButton' toggle.
			async getSubcommands(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const returnOptions: INodePropertyOptions[] = [];
				try {
					// The 'update' command ensures all environments are set up before listing.
					await executeManagerCommand.call(this, 'update');
					const subcommands = await executeManagerCommand.call(this, 'list');
					for (const name in subcommands) {
						if (!subcommands[name].error) {
							returnOptions.push({ name, value: name });
						}
					}
				} catch (error) {
					console.error("Failed to load subcommands:", getErrorMessage(error));
				}
				return returnOptions;
			},

			// This method is triggered when a 'subcommand' is selected.
			// It returns the UI schema to dynamically build the 'Parameters' section.
			getSubcommandParameters: async function(this: ILoadOptionsFunctions): Promise<INodeProperties[]> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) {
					return [];
				}

				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const schema = subcommands[subcommandName]?.input_schema || [];
					// The schema from Python is already in the correct format for n8n properties.
					return schema;
				} catch(error) {
					console.error(`Failed to load parameters for ${subcommandName}:`, getErrorMessage(error));
					return [];
				}
			} as any, // FIX: Cast to 'any' to bypass a strict TypeScript type check. This is a known pattern for dynamically generating UI properties in n8n.
		},
	};


	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const subcommand = this.getNodeParameter('subcommand', 0) as string;
		// The parameters are now a flat object, not nested under 'inputData'.
		const parameters = this.getNodeParameter('parameters', 0) as object;

		// Convert the parameters object to a JSON string for the CLI.
		const inputJsonString = JSON.stringify(parameters);

		// Correctly escape the JSON string for the command line
		const escapedInput = `'${inputJsonString.replace(/'/g, "'\\''")}'`;
		const command = `${subcommand} ${escapedInput}`;

		try {
			const result = await executeManagerCommand.call(this, command);
			const returnData = this.helpers.returnJsonArray(Array.isArray(result) ? result : [result]);
			return [returnData];
		} catch (error) {
			throw new NodeOperationError(this.getNode(), `Execution of '${subcommand}' failed. Error: ${getErrorMessage(error)}`);
		}
	}
}
