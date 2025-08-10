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
    // This path navigates from the dist/nodes/MediaManager folder up to the project root
    const nodeProjectRoot = path.join(currentNodeDir, '..', '..', '..');
    const projectPath = nodeProjectRoot;
    const managerPath = path.join(projectPath, 'manager.py');
    const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
    const venvSubfolder = process.platform === 'win32' ? 'Scripts' : 'bin';
    const pythonPath = path.join(projectPath, 'venv', venvSubfolder, pythonExecutable);

    // This branch handles commands that don't need to stream input data (like 'list' or 'update')
    if (!inputData) {
        const fullCommand = `"${pythonPath}" "${managerPath}" ${command}`;
        try {
            const { stdout, stderr } = await execAsync(fullCommand, { encoding: 'utf-8' });
            if (stderr) console.error(`Manager stderr: ${stderr}`);
            if (command === 'update') return {}; // 'update' command doesn't return JSON
            return JSON.parse(stdout);
        } catch (error: any) {
            console.error(`Error executing command: ${fullCommand}`, error);
            if (error.code === 'ENOENT' || (error.stderr && error.stderr.includes('cannot find the path'))) {
                throw new NodeOperationError(this.getNode(), `Could not find Python. Ensure the setup script has run. Path: ${fullCommand}`);
            }
            throw new NodeOperationError(this.getNode(), `Failed to execute manager.py command: ${command}. Raw Error: ${getErrorMessage(error)}`);
        }
    }

    // This branch handles commands that receive JSON data via stdin
    return new Promise((resolve, reject) => {
        const process = spawn(pythonPath, [managerPath, command]);
        let stdout = '';
        let stderr = '';
        process.stdout.on('data', (data) => stdout += data.toString());
        process.stderr.on('data', (data) => stderr += data.toString());
        process.on('close', (code) => {
            if (stderr) console.error(`Manager stderr: ${stderr}`);
            if (code !== 0) {
                return reject(new NodeOperationError(this.getNode(), `Execution of '${command}' failed with non-zero exit code. Error: ${stderr || 'Unknown error'}`));
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
        icon: 'file:icons/business-icon.svg',
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
                description: 'The Python script to execute.',
            },
            {
                displayName: 'Processing Mode',
                name: 'processingMode',
                type: 'options',
                options: [
                    {
                        name: 'Process Each Item Individually',
                        value: 'single',
                        description: 'Runs the subcommand once for each incoming item.',
                    },
                    {
                        name: 'Process All Items as a Single Batch',
                        value: 'batch',
                        description: 'Runs the subcommand once, sending all items in a single array.',
                    },
                ],
                default: 'single',
                required: true,
                description: 'Choose how to process the incoming data.',
            },
            {
                displayName: 'Parameters',
                name: 'parameters',
                type: 'resourceMapper',
                default: { mappingMode: 'defineBelow', value: null },
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
                try {
                    // FIX: Removed the slow 'update' command from the UI loading process.
                    // The user should run 'python manager.py update' from the CLI when adding/changing tools.
                    const subcommands = await executeManagerCommand.call(this, 'list');
                    return Object.keys(subcommands)
                        .filter(name => !subcommands[name].error)
                        .map(name => ({ name, value: name }));
                } catch (error) {
                    // This is expected if Python/venv is not set up yet. Return empty.
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
                    
                    const pythonSchema = subcommandData?.input_schema || [];

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
                    // Add console logging to help debug if this fails in the future
                    console.error(`Failed to get schema for ${subcommandName}:`, error);
                    return { fields: [] };
                }
            },
        },
    };

    async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
        const items = this.getInputData();
        const subcommand = this.getNodeParameter('subcommand', 0) as string;
        const processingMode = this.getNodeParameter('processingMode', 0) as string;

        if (!subcommand) {
            throw new NodeOperationError(this.getNode(), 'Please select a Subcommand before executing.');
        }

        // --- BATCH PROCESSING LOGIC (CORRECTED) ---
        if (processingMode === 'batch') {
            if (items.length === 0) {
                return [[]];
            }
            try {
                // 1. Create a new array containing ONLY the mapped parameters for each item.
                const mappedItems = items.map((item, index) => {
                    // For each item, get its specific parameters from the UI mapping.
                    const itemParameters = this.getNodeParameter('parameters', index) as { value: object };
                    return itemParameters.value;
                });

                // 2. The input data is now a clean array of mapped parameters.
                const inputData = { '@items': mappedItems };

                const result = await executeManagerCommand.call(this, subcommand, inputData);

                // Note: The output handling here assumes the Python script returns a single
                // JSON object that applies to all items. This might need adjustment later.
                const newItem: INodeExecutionData = {
                    json: { ...items[0].json, ...result },
                    pairedItem: { item: 0 },
                };

                return [this.helpers.returnJsonArray([newItem])];

            } catch (error) {
                if (this.continueOnFail()) {
                    const errorData = items.map(item => ({ json: item.json, error: error as NodeOperationError, pairedItem: item.pairedItem }));
                    return [this.helpers.returnJsonArray(errorData)];
                }
                throw error;
            }
        }

        // --- SINGLE ITEM PROCESSING LOGIC (CORRECTED) ---
        else {
            const returnData: INodeExecutionData[] = [];
            for (let i = 0; i < items.length; i++) {
                try {
                    // This is the correct fix!
                    const itemParameters = this.getNodeParameter('parameters', i) as { value: object };
                    const inputData = { '@item': itemParameters.value };

                    const result = await executeManagerCommand.call(this, subcommand, inputData);

                    // Merge the result with the original item's data.
                    const newItem: INodeExecutionData = {
                        json: { ...items[i].json, ...result },
                        pairedItem: { item: i },
                    };

                    returnData.push(newItem);

                } catch (error) {
                    if (this.continueOnFail()) {
                        returnData.push({ json: items[i].json, error: error as NodeOperationError, pairedItem: { item: i } });
                        continue;
                    }
                    throw error;
                }
            }
            return [this.helpers.returnJsonArray(returnData)];
        }
    }
}
