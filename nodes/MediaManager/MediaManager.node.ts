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
                    // The user should run 'python manager.py update' from the CLI when adding/changing tools.
                    const subcommands = await executeManagerCommand.call(this, 'list');
                    return Object.keys(subcommands)
                        .filter(name => !subcommands[name].error)
                        .map(name => ({ name, value: name }));
                } catch (error) {
                    return [];
                }
            },
        },
        resourceMapping: {
            async getSubcommandSchema(this: ILoadOptionsFunctions): Promise<ResourceMapperFields> {
                const subcommandName = this.getCurrentNodeParameter('subcommand') as string;
                console.log(`[MediaManager] Attempting to load schema for subcommand: '${subcommandName}'`);

                if (!subcommandName) {
                    console.log('[MediaManager] No subcommand selected. Returning empty schema.');
                    return { fields: [] };
                }

                try {
                    const subcommands = await executeManagerCommand.call(this, 'list');
                    console.log('[MediaManager] Received data from manager.py:', JSON.stringify(subcommands, null, 2));

                    const subcommandData = subcommands[subcommandName];
                    console.log(`[MediaManager] Data for '${subcommandName}':`, JSON.stringify(subcommandData, null, 2));
                    
                    const pythonSchema = subcommandData?.input_schema || [];
                    console.log(`[MediaManager] Extracted Python schema:`, JSON.stringify(pythonSchema, null, 2));

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
                    
                    console.log('[MediaManager] Final n8n schema:', JSON.stringify(n8nSchema, null, 2));
                    return { fields: n8nSchema };
                } catch (error) {
                    console.error(`[MediaManager] Failed to get schema for ${subcommandName}:`, error);
                    return { fields: [] };
                }
            },
        },
    };

    async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
        const items = this.getInputData();
        const subcommand = this.getNodeParameter('subcommand', 0) as string;
        const processingMode = this.getNodeParameter('processingMode', 0) as string;
        const parameters = this.getNodeParameter('parameters', 0) as { value: object };

        if (!subcommand) {
            throw new NodeOperationError(this.getNode(), 'Please select a Subcommand before executing.');
        }

        // --- BATCH PROCESSING LOGIC ---
        if (processingMode === 'batch') {
            if (items.length === 0) {
                return [[]]; 
            }
            try {
                const allItemsJson = items.map(item => item.json);
                const inputData = { ...parameters.value, '@items': allItemsJson };
                
                const result = await executeManagerCommand.call(this, subcommand, inputData);
                
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

        // --- SINGLE ITEM PROCESSING LOGIC ---
        else {
            const returnData: INodeExecutionData[] = [];
            for (let i = 0; i < items.length; i++) {
                try {
                    const itemParameters = this.getNodeParameter('parameters', i) as { value: object };
                    const inputData = { ...itemParameters.value, '@item': items[i].json };
                    
                    const result = await executeManagerCommand.call(this, subcommand, inputData);
                    
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
