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
	inputData?: object, // Optional input data for execution
): Promise<any> {
	// --- Fully Automatic Path Detection ---
	const currentNodeDir = __dirname;
	const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');
	const projectPath = nodeProjectRoot;
	const managerPath = path.join(projectPath, 'manager.py');
	const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
	const venvSubfolder = process.platform === 'win32' ? 'Scripts' : 'bin';
	const pythonPath = path.join(projectPath, 'venv', venvSubfolder, pythonExecutable);

	// For simple commands like 'list' and 'update', we can still use exec.
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
				throw new NodeOperationError(this.getNode(), `Could not find the Python script. Please ensure the project's setup script has been run. Path tried: ${fullCommand}`);
			}
			if (error instanceof SyntaxError) {
				throw new NodeOperationError(this.getNode(), `The Python script did not return valid JSON for the command: '${command}'. Raw output: ${error.message}`);
			}
			throw new NodeOperationError(this.getNode(), `Failed to execute manager.py command: ${command}. Raw Error: ${getErrorMessage(error)}`);
		}
	}

	// For executing subcommands with data, use 'spawn' to stream data via stdin.
	return new Promise((resolve, reject) => {
		const process = spawn(pythonPath, [managerPath, command]);
		let stdout = '';
		let stderr = '';

		process.stdout.on('data', (data) => {
			stdout += data.toString();
		});

		process.stderr.on('data', (data) => {
			stderr += data.toString();
		});

		process.on('close', (code) => {
			if (stderr) console.error(`Manager stderr: ${stderr}`);
			if (code !== 0) {
				const error = new NodeOperationError(this.getNode(), `Execution of '${command}' failed with exit code ${code}. Raw Error: ${stderr}`);
				return reject(error);
			}
			try {
				resolve(JSON.parse(stdout));
			} catch (e) {
				const error = new NodeOperationError(this.getNode(), `The Python script did not return valid JSON for the command: '${command}'. Raw output: ${stdout}`);
				reject(error);
			}
		});

		process.on('error', (err) => {
			reject(new NodeOperationError(this.getNode(), `Failed to spawn Python process. Error: ${err.message}`));
		});

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
			// FIX: Removed the faulty displayOptions to resolve the TypeScript error.
			// This notice will now always be visible.
			{
				displayName: 'Hover over parameter fields below to see their description and requirement status.',
				name: 'descriptionNotice',
				type: 'notice',
				default: '',
			},
			{
				displayName: 'Subcommand',
				name: 'subcommand',
				type: 'options',
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
			async getSubcommandSchema(this: ILoadOptionsFunctions): Promise<ResourceMapperFields> {
				const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
				if (!subcommandName) return { fields: [] };

				try {
					const subcommands = await executeManagerCommand.call(this, 'list');
					const pythonSchema = subcommands[subcommandName]?.input_schema || [];

					const n8nSchema: ResourceMapperField[] = pythonSchema.map((field: any) => {
						const n8nField: Omit<ResourceMapperField, 'default'> & { default?: any; options?: any, description?: string } = {
							id: field.name,
							displayName: field.displayName,
							required: field.required || false,
							display: true,
							type: field.type || 'string',
							defaultMatch: false,
							description: field.description || '', // Pass the description for hover text
						};

						if (field.type === 'options' && Array.isArray(field.options)) {
							n8nField.options = field.options;
						}

						if (field.default !== undefined) {
							n8nField.default = field.default;
						}

						return n8nField as ResourceMapperField;
					});
					
					return { fields: n8nSchema };
				} catch (error) {
					console.error(`Failed to load schema for ${subcommandName}:`, getErrorMessage(error));
					return { fields: [] };
				}
			},
		},
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];

		for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
			try {
				const subcommand = this.getNodeParameter('subcommand', itemIndex) as string;
				const parameters = this.getNodeParameter('parameters', itemIndex) as { value: object };
				const inputData = parameters.value || {};

				const result = await executeManagerCommand.call(this, subcommand, inputData);
				
				const newItem: INodeExecutionData = {
					json: { ...items[itemIndex].json, ...result },
					pairedItem: { item: itemIndex },
				};
				
				returnData.push(newItem);

			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({ json: this.getInputData(itemIndex)[0].json, error: error as NodeOperationError });
					continue;
				}
				throw error;
			}
		}

		return [returnData];
	}
}
