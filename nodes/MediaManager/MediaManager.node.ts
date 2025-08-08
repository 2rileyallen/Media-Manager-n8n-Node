import {
	IExecuteFunctions,
	INodeType,
	INodeTypeDescription,
	ILoadOptionsFunctions,
	INodeExecutionData,
	NodeOperationError,
	INodePropertyOptions,
	INodeProperties,
	NodeConnectionType, // FIX: Import the explicit type for connections.
} from 'n8n-workflow';

import { promisify } from 'util';
import { exec } from 'child_process';

const execAsync = promisify(exec);

/**
 * Executes a command for the manager.py script and handles parsing.
 * @param command The command to run (e.g., 'list', 'update')
 */
async function executeManagerCommand(
	this: IExecuteFunctions | ILoadOptionsFunctions,
	command: string,
): Promise<any> {
	// These parameters are required and are fetched from the node's UI.
	const managerPath = this.getNodeParameter('managerPath', 0, '') as string;
	if (!managerPath) {
		throw new NodeOperationError(this.getNode(), 'Manager.py path is not configured. Please set it in the node settings.');
	}

	const pythonPath = this.getNodeParameter('pythonPath', 0, '') as string;
	if (!pythonPath) {
		throw new NodeOperationError(this.getNode(), 'Python path is not configured. Please set it in the node settings.');
	}

	const fullCommand = `${pythonPath} "${managerPath}" ${command}`;

	try {
		const { stdout, stderr } = await execAsync(fullCommand, { encoding: 'utf-8' });
		if (stderr) {
			// Stderr is used for progress and logging, so we just log it to the console.
			console.error(`Manager stderr: ${stderr}`);
		}
		// The manager.py script is now guaranteed to return JSON on stdout
		return JSON.parse(stdout);
	} catch (error) {
		console.error(`Error executing command: ${fullCommand}`, error);
		// The actual error message from the script is often in stderr, which is more useful.
		throw new NodeOperationError(this.getNode(), `Failed to execute manager.py command: ${command}. Raw Error: ${error.stderr || error.message}`);
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
		// FIX: Use the explicit NodeConnectionType enum to satisfy strict n8n types.
		inputs: [NodeConnectionType.Main],
		outputs: [NodeConnectionType.Main],
		properties: [
			// --- Static Configuration ---
			{
				displayName: 'Manager.py Path',
				name: 'managerPath',
				type: 'string',
				default: '',
				required: true,
				placeholder: '/path/to/your/media_manager/manager.py',
				description: 'The absolute path to the manager.py script.',
			},
			{
				displayName: 'Python Path',
				name: 'pythonPath',
				type: 'string',
				default: '',
				required: true,
				description: 'The path to the Python executable in the main venv. Use an absolute path for reliability in n8n.',
				placeholder: '/path/to/your/media_manager/venv/bin/python',
			},

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
					// This makes the dropdown reload when the refresh button is used
					loadOptionsDependsOn: ['refreshButton'],
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
							// This makes the parameters reload when a new subcommand is chosen
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
			/**
			 * Fetches the list of available subcommands from manager.py
			 */
			async getSubcommands(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const returnOptions: INodePropertyOptions[] = [];
				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					for (const name in subcommands) {
						if (!subcommands[name].error) {
							returnOptions.push({ name, value: name });
						}
					}
				} catch (error) {
					console.error("Failed to load subcommands:", error.message);
				}
				return returnOptions;
			},

			/**
			 * Fetches the INPUT_SCHEMA for a selected subcommand and transforms it
			 * into n8n UI fields.
			 */
			// The return type is set to `any` as a targeted fix for this specific
			// function. This is necessary because it returns INodeProperties[] for a 'json'
			// field, which differs from the general index signature for loadOptions methods.
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
					console.error(`Failed to load parameters for ${subcommandName}:`, error.message);
					return [];
				}
			} as any, // The targeted 'any' cast to resolve the type conflict.
		},
	};


	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const subcommand = this.getNodeParameter('subcommand', 0) as string;
		const parameters = this.getNodeParameter('parameters', 0) as { inputData?: string };

		let inputJsonString = '{}';
		if (parameters.inputData) {
			try {
				const parsedInput = JSON.parse(parameters.inputData);
				inputJsonString = JSON.stringify(parsedInput);
			} catch (error) {
				throw new NodeOperationError(this.getNode(), 'Input Data is not valid JSON.');
			}
		}

		const escapedInput = `'${inputJsonString}'`;
		const command = `${subcommand} ${escapedInput}`;

		try {
			const result = await executeManagerCommand.call(this, command);
			const returnData = this.helpers.returnJsonArray(Array.isArray(result) ? result : [result]);
			return [returnData];
		} catch (error) {
			throw new NodeOperationError(this.getNode(), `Execution of '${subcommand}' failed. Error: ${error.message}`);
		}
	}
}
