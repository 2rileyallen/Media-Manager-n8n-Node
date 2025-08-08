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
import { exec, spawn } from 'child_process';
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
	inputData?: object,
): Promise<any> {
	const currentNodeDir = __dirname;
	const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');
	const projectPath = nodeProjectRoot;
	const managerPath = path.join(projectPath, 'manager.py');
	const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
	const venvSubfolder = process.platform === 'win32' ? 'Scripts' : 'bin';
	const pythonPath = path.join(projectPath, 'venv', venvSubfolder, pythonExecutable);

	if (!inputData) {
		const fullCommand = `"${pythonPath}" "${managerPath}" ${command}`;
		try {
			const { stdout, stderr } = await execAsync(fullCommand, { encoding: 'utf-8' });
			if (stderr) console.error(`Manager stderr: ${stderr}`);
			if (command === 'update') return {};
			return JSON.parse(stdout);
		} catch (error: any) {
			console.error(`Error executing command: ${fullCommand}`, error);
			if (error.code === 'ENOENT' || (error.stderr && error.stderr.includes('cannot find the path'))) {
				throw new NodeOperationError(this.getNode(), `Could not find Python. Ensure the setup script has run. Path: ${fullCommand}`);
			}
			throw new NodeOperationError(this.getNode(), `Failed to execute manager.py command: ${command}. Raw Error: ${getErrorMessage(error)}`);
		}
	}

	return new Promise((resolve, reject) => {
		const process = spawn(pythonPath, [managerPath, command]);
		let stdout = '';
		let stderr = '';
		process.stdout.on('data', (data) => stdout += data.toString());
		process.stderr.on('data', (data) => stderr += data.toString());
		process.on('close', (code) => {
			if (stderr) console.error(`Manager stderr: ${stderr}`);
			if (code !== 0) {
				return reject(new NodeOperationError(this.getNode(), `Execution of '${command}' failed. Error: ${stderr}`));
			}
			try {
				resolve(JSON.parse(stdout));
			} catch (e) {
				reject(new NodeOperationError(this.getNode(), `Python script did not return valid JSON for '${command}'. Output: ${stdout}`));
			}
		});
		process.on('error', (err) => reject(new NodeOperationError(this.getNode(), `Failed to spawn Python process. Error: ${err.message}`)));
		process.stdin.write(JSON.stringify(inputData));
		process.stdin.end();
	});
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
				displayName: 'Subcommand',
				name: 'subcommand',
				type: 'options',
				typeOptions: { loadOptionsMethod: 'getSubcommands' },
				default: '',
				required: true,
			},
			// ADDED: A dropdown to select the processing mode.
			{
				displayName: 'Processing Mode',
				name: 'processingMode',
				type: 'options',
				typeOptions: { loadOptionsMethod: 'getProcessingModes' },
				default: '',
				description: 'Choose how to process the incoming data.',
				displayOptions: {
					// This dropdown only appears if the selected subcommand *has* modes.
					show: {
						'@modesExist': [true], // FIX: Use a simple boolean check
					},
				},
			},
			// This resourceMapper is for SINGLE item processing.
			{
				displayName: 'Parameters',
				name: 'parametersSingle',
				type: 'resourceMapper',
				default: { mappingMode: 'defineBelow', value: null },
				typeOptions: {
					loadOptionsDependsOn: ['subcommand', 'processingMode'],
					resourceMapper: {
						resourceMapperMethod: 'getSubcommandSchema',
						mode: 'add',
						fieldWords: { singular: 'parameter', plural: 'parameters' },
					},
				},
				displayOptions: {
					show: {
						// Show this if EITHER the subcommand has no modes OR the 'single' mode is selected.
						'@modesExist': [false],
						processingMode: ['single', ''], // Also show for default empty value
					},
				},
			},
			// This resourceMapper is for BATCH processing.
			{
				displayName: 'Parameters',
				name: 'parametersBatch',
				type: 'resourceMapper',
				default: { mappingMode: 'defineBelow', value: null },
				typeOptions: {
					loadOptionsDependsOn: ['subcommand', 'processingMode'],
					resourceMapper: {
						resourceMapperMethod: 'getSubcommandSchema',
						mode: 'add',
						fieldWords: { singular: 'parameter', plural: 'parameters' },
					},
				},
				displayOptions: {
					show: {
						// Only show this if the 'batch' mode is selected.
						processingMode: ['batch'],
					},
				},
			},
		],
	};

	// These are hidden properties used to store the full schema for display logic.
	// This is a standard n8n pattern for complex dynamic UIs.
	protected static hiddenProperties = {
		'@modesExist': {
			displayName: 'Modes Exist Flag',
			name: '@modesExist',
			type: 'boolean',
			default: false,
			typeOptions: { loadOptionsMethod: 'getHiddenModesExist' },
		},
	};

	methods = {
		// FIX: Cast to 'any' to bypass strict type check for the helper method.
		loadOptions: {
			async getSubcommands(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				try {
					await executeManagerCommand.call(this, 'update');
					const subcommands = await executeManagerCommand.call(this, 'list');
					return Object.keys(subcommands)
						.filter(name => !subcommands[name].error)
						.map(name => ({ name, value: name }));
				} catch (error) {
					return [];
				}
			},
			// This method populates the "Processing Mode" dropdown.
			async getProcessingModes(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return [];
				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const modes = subcommands[subcommandName]?.modes;
					if (!modes) return [];
					return Object.keys(modes).map(modeName => ({
						name: modes[modeName].displayName || modeName,
						value: modeName,
					}));
				} catch (error) {
					return [];
				}
			},
			// This loads a simple boolean into a hidden field for the displayOptions to use.
			async getHiddenModesExist(this: ILoadOptionsFunctions): Promise<boolean> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return false;
				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const modes = subcommands[subcommandName]?.modes;
					return modes && Object.keys(modes).length > 0;
				} catch (error) {
					return false;
				}
			},
		} as any,
		resourceMapping: {
			async getSubcommandSchema(this: ILoadOptionsFunctions): Promise<ResourceMapperFields> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return { fields: [] };

				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const subcommandData = subcommands[subcommandName];
					if (!subcommandData) return { fields: [] };

					let pythonSchema: any[] = [];
					// Check if the subcommand uses modes.
					if (subcommandData.modes) {
						const mode = this.getCurrentNodeParameter('processingMode') as string | undefined;
						// If mode is not selected yet, or is 'single', default to single.
						const effectiveMode = mode || 'single';
						pythonSchema = subcommandData.modes[effectiveMode]?.input_schema || [];
					} else {
						// Fallback to the top-level schema for simple nodes.
						pythonSchema = subcommandData.input_schema || [];
					}

					const n8nSchema: ResourceMapperField[] = pythonSchema.map((field: any) => ({
						id: field.name,
						displayName: field.displayName,
						required: field.required || false,
						display: true,
						type: field.type || 'string',
						defaultMatch: false,
						description: field.description || '',
						options: field.options,
						default: field.default,
					}));
					
					return { fields: n8nSchema };
				} catch (error) {
					return { fields: [] };
				}
			},
		},
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];
		const subcommand = this.getNodeParameter('subcommand', 0) as string;
		const processingMode = this.getNodeParameter('processingMode', 0) as string;

		// Determine if we are in batch mode.
		const isBatchMode = processingMode === 'batch';

		if (isBatchMode) {
			// BATCH MODE: Process all items as a single unit.
			try {
				const allJsonData = items.map(item => item.json);
				const parameters = this.getNodeParameter('parametersBatch', 0) as { value: object };
				// Pass the mode and the full list of items to Python.
				const inputData = { ...parameters.value, '@items': allJsonData, '@mode': processingMode };
				const result = await executeManagerCommand.call(this, subcommand, inputData);
				returnData.push({ json: result });
			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({ json: {}, error: error as NodeOperationError });
				} else {
					throw error;
				}
			}
		} else {
			// SINGLE ITEM MODE: Loop through each item individually.
			for (let i = 0; i < items.length; i++) {
				try {
					const parameters = this.getNodeParameter('parametersSingle', i) as { value: object };
					// Pass the mode and the current item's data.
					const inputData = { ...parameters.value, '@item': items[i].json, '@mode': processingMode || 'single' };
					const result = await executeManagerCommand.call(this, subcommand, inputData);
					returnData.push({ json: { ...items[i].json, ...result }, pairedItem: { item: i } });
				} catch (error) {
					if (this.continueOnFail()) {
						returnData.push({ json: items[i].json, error: error as NodeOperationError });
						continue;
					}
					throw error;
				}
			}
		}

		return [this.helpers.returnJsonArray(returnData)];
	}
}
