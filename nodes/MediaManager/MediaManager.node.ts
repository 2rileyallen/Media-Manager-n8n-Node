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
				if (stdout.trim() === '') return resolve({});
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
			{
				displayName: 'Processing Mode',
				name: 'processingMode',
				type: 'options',
				typeOptions: {
					loadOptionsMethod: 'getProcessingModes',
					loadOptionsDependsOn: ['subcommand'],
				},
				default: '', // Default to empty to force a selection
				description: 'Choose how to process data. This appears only if the subcommand supports multiple modes.',
				// This field is now automatically hidden by n8n if getProcessingModes returns an empty array.
			},
			{
				displayName: 'Parameters',
				name: 'parameters',
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
			},
		],
	};

	methods = {
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
			async getProcessingModes(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return [];
				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const modes = subcommands[subcommandName]?.modes;
					// If no modes are defined, return an empty array. n8n will hide the field.
					if (!modes || Object.keys(modes).length === 0) {
						return [];
					}
					return Object.keys(modes).map(modeName => ({
						name: modes[modeName].displayName || modeName,
						value: modeName,
					}));
				} catch (error) {
					return [];
				}
			},
		},
		resourceMapping: {
			async getSubcommandSchema(this: ILoadOptionsFunctions): Promise<ResourceMapperFields> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return { fields: [] };

				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const subcommandData = subcommands[subcommandName];
					if (!subcommandData) return { fields: [] };

					let pythonSchema: any[] = [];
					const processingMode = this.getCurrentNodeParameter('processingMode') as string;

					if (subcommandData.modes) {
						// If a mode is selected, use its schema.
						if (processingMode && subcommandData.modes[processingMode]) {
							pythonSchema = subcommandData.modes[processingMode].input_schema || [];
						}
						// If no mode is selected yet, return an empty schema to wait for user input.
					} else {
						// For simple nodes, use the top-level schema.
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

		for (let i = 0; i < items.length; i++) {
			try {
				const subcommand = this.getNodeParameter('subcommand', i) as string;
				const processingMode = this.getNodeParameter('processingMode', i) as string;
				const parameters = this.getNodeParameter('parameters', i) as { value: object };
				
				const inputData = { ...parameters.value, '@item': items[i].json, '@mode': processingMode || 'single' };
				
				const result = await executeManagerCommand.call(this, subcommand, inputData);
				
				const newItem: INodeExecutionData = {
					json: { ...items[i].json, ...result },
					pairedItem: { item: i },
				};

				returnData.push(newItem);

			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({ json: items[i].json, error: error as NodeOperationError });
					continue;
				}
				throw error;
			}
		}

		return [this.helpers.returnJsonArray(returnData)];
	}
}
