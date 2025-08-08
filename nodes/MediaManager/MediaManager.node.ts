import {
	IExecuteFunctions,
	INodeType,
	INodeTypeDescription,
	ILoadOptionsFunctions,
	INodeExecutionData,
	NodeOperationError,
	INodePropertyOptions,
	ResourceMapperField,
	ResourceMapperFields,
	NodeConnectionType,
} from 'n8n-workflow';

import { promisify } from 'util';
import { exec } from 'child_process';
import * as path from 'path';

const execAsync = promisify(exec);

// --- Helper Functions ---

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

async function executeManagerCommand(
	this: IExecuteFunctions | ILoadOptionsFunctions,
	command: string,
): Promise<any> {
	// --- Fully Automatic Path Detection ---
	const currentNodeDir = __dirname;
	const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');

	// The python project is the node project itself, not a sibling.
	const projectPath = nodeProjectRoot;

	const managerPath = path.join(projectPath, 'manager.py');
	const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
	const venvSubfolder = process.platform === 'win32' ? 'Scripts' : 'bin';
	const pythonPath = path.join(projectPath, 'venv', venvSubfolder, pythonExecutable);
	const fullCommand = `"${pythonPath}" "${managerPath}" ${command}`;

	try {
		const { stdout, stderr } = await execAsync(fullCommand, { encoding: 'utf-8' });
		if (stderr) console.error(`Manager stderr: ${stderr}`);
		
		// FIX: The 'update' command does not return JSON, so we handle it separately.
		if (command === 'update') {
			return {}; // Return an empty object to signify success without data.
		}

		return JSON.parse(stdout);
	} catch (error: any) {
		console.error(`Error executing command: ${fullCommand}`, error);
		if (error.code === 'ENOENT' || (error.stderr && error.stderr.includes('cannot find the path'))) {
			throw new NodeOperationError(this.getNode(), `Could not find the Python script. Please ensure the project's setup script has been run. Path tried: ${fullCommand}`);
		}
		// Check for JSON parsing errors specifically
		if (error instanceof SyntaxError) {
			throw new NodeOperationError(this.getNode(), `The Python script did not return valid JSON for the command: '${command}'. Raw output: ${error.message}`);
		}
		throw new NodeOperationError(this.getNode(), `Failed to execute manager.py command: ${command}. Raw Error: ${getErrorMessage(error)}`);
	}
}

// --- Main Node Class ---

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
			// FIX: The refresh button has been removed for a cleaner UI.
			{
				displayName: 'Subcommand',
				name: 'subcommand',
				type: 'options',
				// The loadOptionsMethod will now run automatically when the node panel is opened.
				typeOptions: {
					loadOptionsMethod: 'getSubcommands',
				},
				default: '',
				required: true,
				description: 'Choose the subcommand to run.',
			},
			{
				displayName: 'Parameters',
				name: 'parameters',
				type: 'resourceMapper',
				default: { mappingMode: 'defineBelow', value: null },
				description: 'The parameters for the selected subcommand.',
				typeOptions: {
					loadOptionsDependsOn: ['subcommand'],
					resourceMapper: {
						resourceMapperMethod: 'getSubcommandSchema',
						mode: 'add',
						fieldWords: { singular: 'parameter', plural: 'parameters' },
					},
				},
			},
		],
	};

	methods = {
		loadOptions: {
			// This method now runs automatically when the node UI is opened.
			async getSubcommands(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const returnOptions: INodePropertyOptions[] = [];
				try {
					// It runs the update command to ensure the list is fresh.
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
		},
		resourceMapping: {
			async getSubcommandSchema(this: ILoadOptionsFunctions): Promise<ResourceMapperFields> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return { fields: [] };

				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const pythonSchema = subcommands[subcommandName]?.input_schema || [];

					const n8nSchema: ResourceMapperField[] = pythonSchema.map((field: any) => ({
						id: field.name,
						displayName: field.displayName,
						required: field.required || false,
						display: true,
						type: field.type || 'string',
					}));
					
					return { fields: n8nSchema };
				} catch (error) {
					console.error(`Failed to load schema for ${subcommandName}:`, getErrorMessage(error));
					return { fields: [] };
				}
			},
		},
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const subcommand = this.getNodeParameter('subcommand', 0) as string;
		const parameters = this.getNodeParameter('parameters', 0) as { value: object };
		const inputData = parameters.value || {};

		const inputJsonString = JSON.stringify(inputData);
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
