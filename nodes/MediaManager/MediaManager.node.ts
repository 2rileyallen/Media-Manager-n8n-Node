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
	// Get the directory of the currently executing file (e.g., .../dist/nodes/MediaManager)
	const currentNodeDir = __dirname;

	// The root of the n8n node project is 3 levels up
	const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');

	// The python project is a sibling folder to the n8n node project
	const projectPath = path.join(nodeProjectRoot, '..', 'media_manager');

	const managerPath = path.join(projectPath, 'manager.py');

	// Determine the correct path to the Python executable within the main `venv`
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
			{
				displayName: 'Refresh Subcommand List',
				name: 'refreshButton',
				type: 'notice',
				default: '',
				description: 'Click the refresh button below to scan the subcommands folder for any new or deleted tools.',
			},

			// --- Subcommand Selection Dropdown ---
			{
				displayName: 'Subcommand',
				name: 'subcommand',
				type: 'options',
				typeOptions: {
					loadOptionsMethod: 'getSubcommands',
					loadOptionsDependsOn: ['refreshButton'], // No longer depends on any path input
				},
				default: '',
				required: true,
				description: 'Choose the subcommand to run.',
			},

			// --- Dynamic Parameter Section ---
			{
				displayName: 'Parameters',
				name: 'parameters',
				type: 'collection',
				placeholder: 'Add Parameter',
				default: {},
				options: [
					{
						displayName: 'Input Data',
						name: 'inputData',
						type: 'json',
						typeOptions: {
							loadOptionsMethod: 'getSubcommandParameters',
							loadOptionsDependsOn: ['subcommand'],
						},
						default: '{}',
						description: 'Input data for the selected subcommand.',
					},
				],
			},
		],
	};

	methods = {
		loadOptions: {
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

			getSubcommandParameters: async function(this: ILoadOptionsFunctions): Promise<INodeProperties[]> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) {
					return [];
				}

				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const schema = subcommands[subcommandName]?.input_schema || [];
					return schema;
				} catch(error) {
					console.error(`Failed to load parameters for ${subcommandName}:`, getErrorMessage(error));
					return [];
				}
			} as any,
		},
	};


	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const subcommand = this.getNodeParameter('subcommand', 0) as string;
		const parameters = this.getNodeParameter('parameters', 0) as { inputData?: string };

		let inputJsonString = '{}';
		if (parameters.inputData) {
			try {
				inputJsonString = parameters.inputData;
			} catch (error) {
				throw new NodeOperationError(this.getNode(), 'Input Data is not valid JSON.');
			}
		}

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
