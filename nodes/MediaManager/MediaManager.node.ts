import {
	IExecuteFunctions,
	INodeType,
	INodeTypeDescription,
	ILoadOptionsFunctions,
	INodeExecutionData,
	NodeOperationError,
	INodePropertyOptions,
	ResourceMapperField,
	ResourceMapperFields, // FIX: Import the correct wrapper type
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
	const currentNodeDir = __dirname;
	const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');
	const projectPath = path.join(nodeProjectRoot, '..', 'media_manager');
	const managerPath = path.join(projectPath, 'manager.py');
	const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
	const venvSubfolder = process.platform === 'win32' ? 'Scripts' : 'bin';
	const pythonPath = path.join(projectPath, 'venv', venvSubfolder, pythonExecutable);
	const fullCommand = `"${pythonPath}" "${managerPath}" ${command}`;

	try {
		const { stdout, stderr } = await execAsync(fullCommand, { encoding: 'utf-8' });
		if (stderr) console.error(`Manager stderr: ${stderr}`);
		return JSON.parse(stdout);
	} catch (error: any) {
		console.error(`Error executing command: ${fullCommand}`, error);
		// Provide a more helpful error message if the path is not found
		if (error.code === 'ENOENT' || (error.stderr && error.stderr.includes('cannot find the path'))) {
			throw new NodeOperationError(this.getNode(), `Could not find the Python script. Please ensure the 'media_manager' project is in the correct location and its setup script has been run. Path tried: ${fullCommand}`);
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
			{
				displayName: 'Refresh Subcommand List',
				name: 'refreshButton',
				type: 'boolean',
				default: false,
				description: 'Toggle this switch to re-scan the subcommands folder for any new or deleted tools.',
			},
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
			async getSubcommands(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const returnOptions: INodePropertyOptions[] = [];
				try {
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
			// FIX: The return type is now Promise<ResourceMapperFields>
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
					
					// FIX: Return the array inside a 'fields' object
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
