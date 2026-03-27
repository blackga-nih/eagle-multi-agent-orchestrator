/**
 * MCP Agent Configurations
 *
 * Defines the specialized agents with their MCP server connections,
 * system prompts, and visual styling.
 */

import { AgentConfig, AgentType } from '@/types/mcp';
import { UserRole } from '@/types/schema';

export const AGENT_CONFIGS: Record<AgentType, AgentConfig> = {
  frontend: {
    id: 'frontend',
    name: 'Frontend Expert',
    description: 'UI/UX, React, TypeScript, CSS specialist',
    systemPrompt: `You are a Frontend Expert specializing in modern web development.
Your expertise includes:
- React and Next.js applications
- TypeScript and JavaScript
- Tailwind CSS and modern styling
- Component architecture and design patterns
- Accessibility and responsive design
- Performance optimization

When helping users, you can:
- Read and analyze frontend code files
- Suggest improvements and best practices
- Debug UI issues and styling problems
- Review component implementations

Always provide clear, actionable advice with code examples when appropriate.`,
    mcpServers: [
      { name: 'filesystem', url: 'http://localhost:8080/mcp', description: 'File system access' },
      {
        name: 'browser-tools',
        url: 'http://localhost:8082/mcp',
        description: 'Browser inspection',
      },
    ],
    icon: 'Palette',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    mockTools: ['read_file', 'list_files', 'search_code', 'inspect_element', 'get_styles'],
  },
  backend: {
    id: 'backend',
    name: 'Backend Expert',
    description: 'Python, APIs, database specialist',
    systemPrompt: `You are a Backend Expert specializing in server-side development.
Your expertise includes:
- Python and Node.js development
- RESTful API design and implementation
- PostgreSQL and database optimization
- Authentication and authorization
- Microservices architecture
- Error handling and logging

When helping users, you can:
- Query and analyze database schemas
- Read and review backend code
- Suggest API improvements
- Debug server-side issues
- Optimize database queries

Always explain your reasoning and provide production-ready solutions.`,
    mcpServers: [
      { name: 'postgres', url: 'http://localhost:8081/mcp', description: 'PostgreSQL database' },
      { name: 'filesystem', url: 'http://localhost:8080/mcp', description: 'File system access' },
    ],
    icon: 'Server',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    mockTools: ['query_database', 'read_file', 'list_tables', 'describe_table', 'run_sql'],
  },
  aws_admin: {
    id: 'aws_admin',
    name: 'AWS Admin',
    description: 'Infrastructure and cloud operations',
    systemPrompt: `You are an AWS Infrastructure Expert specializing in cloud operations for the NCI OA Agent.

Your expertise includes:
- AWS services (EC2, ECS, Lambda, S3, RDS, Aurora, Bedrock)
- CloudWatch logs analysis and metrics monitoring
- Infrastructure monitoring and alerting
- Cost optimization and budget management
- Security best practices and IAM
- CDK and CloudFormation deployments

When helping users, you have access to real AWS tools:

**CloudWatch Tools (query_logs, get_metrics, list_alarms, get_log_groups):**
- Query CloudWatch Logs using Insights syntax
- Retrieve metrics for any AWS service
- List and create alarms for monitoring

**AWS CLI Tools (describe_instances, describe_ecs_services, list_lambda_functions, describe_stack):**
- Describe EC2 instances and their status
- Check ECS services and task counts
- List Lambda functions and configurations
- View CloudFormation stack outputs

Always prioritize security and cost-effectiveness in your recommendations.
Use the available tools to provide accurate, real-time information about the infrastructure.`,
    mcpServers: [
      {
        name: 'cloudwatch',
        url: 'http://localhost:8083/mcp',
        description: 'CloudWatch logs, metrics, and alarms',
      },
      {
        name: 'aws-cli',
        url: 'http://localhost:8084/mcp',
        description: 'EC2, ECS, Lambda, CloudFormation',
      },
    ],
    icon: 'Cloud',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    mockTools: [
      'query_logs',
      'get_metrics',
      'list_alarms',
      'get_log_groups',
      'describe_instances',
      'describe_ecs_services',
      'list_lambda_functions',
      'describe_stack',
    ],
  },
  analyst: {
    id: 'analyst',
    name: 'Data Analyst',
    description: 'Data analysis and reporting specialist',
    systemPrompt: `You are a Data Analyst Expert specializing in data analysis and reporting.
Your expertise includes:
- SQL and data querying
- Data visualization
- Statistical analysis
- Report generation
- Business intelligence
- Data quality assessment

When helping users, you can:
- Run complex SQL queries
- Analyze data patterns and trends
- Generate data exports
- Create summary reports
- Identify data anomalies

Always validate your findings and provide clear explanations of your analysis.`,
    mcpServers: [
      { name: 'postgres', url: 'http://localhost:8081/mcp', description: 'PostgreSQL database' },
      {
        name: 'filesystem',
        url: 'http://localhost:8080/mcp',
        description: 'File system for exports',
      },
    ],
    icon: 'BarChart3',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
    mockTools: ['run_sql', 'export_csv', 'create_chart', 'analyze_data', 'generate_report'],
  },
};

export const AGENT_ORDER: AgentType[] = ['frontend', 'backend', 'aws_admin', 'analyst'];

/**
 * Check if mock mode is enabled.
 * In mock mode, we simulate MCP server responses.
 */
export const USE_MOCK_MCP = process.env.NEXT_PUBLIC_MOCK_MCP !== 'false';

/**
 * Mock tool definitions for development.
 */
export const MOCK_TOOL_DEFINITIONS: Record<string, { name: string; description: string }[]> = {
  frontend: [
    { name: 'read_file', description: 'Read the contents of a file' },
    { name: 'list_files', description: 'List files in a directory' },
    { name: 'search_code', description: 'Search for code patterns across files' },
    { name: 'inspect_element', description: 'Inspect DOM element properties' },
    { name: 'get_styles', description: 'Get computed styles for an element' },
  ],
  backend: [
    { name: 'query_database', description: 'Execute a read-only SQL query' },
    { name: 'read_file', description: 'Read the contents of a file' },
    { name: 'list_tables', description: 'List all tables in the database' },
    { name: 'describe_table', description: 'Get schema for a table' },
    { name: 'run_sql', description: 'Execute a SQL statement' },
  ],
  aws_admin: [
    { name: 'query_logs', description: 'Query CloudWatch Logs using Insights syntax' },
    { name: 'get_metrics', description: 'Retrieve CloudWatch metrics for any AWS service' },
    { name: 'list_alarms', description: 'List CloudWatch alarms with current states' },
    { name: 'get_log_groups', description: 'List CloudWatch Log Groups' },
    { name: 'describe_instances', description: 'List and describe EC2 instances' },
    { name: 'describe_ecs_services', description: 'Describe ECS services in a cluster' },
    { name: 'list_lambda_functions', description: 'List Lambda functions' },
    { name: 'describe_stack', description: 'Describe a CloudFormation stack' },
    { name: 'list_ecs_clusters', description: 'List all ECS clusters' },
    { name: 'get_caller_identity', description: 'Get AWS account ID and identity' },
  ],
  analyst: [
    { name: 'run_sql', description: 'Execute a SQL query for analysis' },
    { name: 'export_csv', description: 'Export query results to CSV' },
    { name: 'create_chart', description: 'Generate a chart from data' },
    { name: 'analyze_data', description: 'Perform statistical analysis' },
    { name: 'generate_report', description: 'Create a summary report' },
  ],
};

/**
 * Generate a mock response for an agent.
 */
export function generateMockResponse(
  agentId: AgentType,
  userMessage: string,
  includeToolCall: boolean = false,
): {
  content: string;
  toolCalls?: { name: string; args: Record<string, unknown>; result: unknown }[];
} {
  const config = AGENT_CONFIGS[agentId];
  const tools = MOCK_TOOL_DEFINITIONS[agentId];

  let content = '';
  let toolCalls: { name: string; args: Record<string, unknown>; result: unknown }[] | undefined;

  if (includeToolCall && tools.length > 0) {
    const tool = tools[Math.floor(Math.random() * tools.length)];
    toolCalls = [
      {
        name: tool.name,
        args: { query: userMessage },
        result: getMockToolResult(tool.name, agentId),
      },
    ];
  }

  switch (agentId) {
    case 'frontend':
      content = `As a Frontend Expert, I can help you with that.

${
  includeToolCall
    ? `I used the **${toolCalls?.[0]?.name}** tool to gather information.

`
    : ''
}Based on your question about "${userMessage.slice(0, 50)}...", here's my analysis:

1. **Component Structure**: Consider using a modular approach with separate concerns
2. **Styling**: Tailwind CSS classes can be optimized for better maintainability
3. **Performance**: Lazy loading and memoization where appropriate

Would you like me to dive deeper into any of these areas?`;
      break;

    case 'backend':
      content = `As a Backend Expert, I'll help you address this.

${
  includeToolCall
    ? `I executed the **${toolCalls?.[0]?.name}** tool.

`
    : ''
}Regarding "${userMessage.slice(0, 50)}...", here's what I found:

1. **API Design**: RESTful patterns with proper error handling
2. **Database**: Indexed queries for optimal performance
3. **Security**: Input validation and parameterized queries

Let me know if you need specific code examples or further clarification.`;
      break;

    case 'aws_admin':
      content = `As an AWS Admin, I'll investigate this for you.

${
  includeToolCall
    ? `I ran the **${toolCalls?.[0]?.name}** tool to check the infrastructure.

`
    : ''
}For your question about "${userMessage.slice(0, 50)}...", here's my assessment:

1. **Resources**: All services are operating normally
2. **Logs**: No critical errors in the last 24 hours
3. **Metrics**: CPU and memory usage within acceptable limits

Would you like me to drill down into any specific service or metric?`;
      break;

    case 'analyst':
      content = `As a Data Analyst, I can help analyze this.

${
  includeToolCall
    ? `I used the **${toolCalls?.[0]?.name}** tool to query the data.

`
    : ''
}Based on your request about "${userMessage.slice(0, 50)}...", here are my findings:

1. **Data Quality**: The dataset is complete with minimal null values
2. **Trends**: There's a positive trend in the key metrics
3. **Recommendations**: Consider segmenting by category for deeper insights

Would you like me to generate a detailed report or export the data?`;
      break;
  }

  return { content, toolCalls };
}

function getMockToolResult(toolName: string, agentId: AgentType): unknown {
  const mockResults: Record<string, unknown> = {
    // Frontend tools
    read_file: { content: '// Sample file content\nexport function example() { ... }', lines: 42 },
    list_files: { files: ['index.tsx', 'styles.css', 'utils.ts'], count: 3 },
    search_code: {
      matches: [{ file: 'app.tsx', line: 15, content: 'const result = ...' }],
      total: 1,
    },
    // Backend tools
    query_database: { rows: [{ id: 1, name: 'Sample', value: 100 }], rowCount: 1 },
    list_tables: { tables: ['users', 'workflows', 'documents'], count: 3 },
    describe_table: { columns: ['id', 'name', 'created_at'], primaryKey: 'id' },
    // CloudWatch tools
    query_logs: {
      results: [
        {
          '@timestamp': new Date().toISOString(),
          '@message': 'INFO: Request processed successfully',
          level: 'INFO',
        },
      ],
      rowCount: 1,
    },
    get_metrics: {
      datapoints: [{ timestamp: new Date().toISOString(), value: 42.5, unit: 'Percent' }],
      label: 'CPUUtilization',
      namespace: 'AWS/ECS',
    },
    list_alarms: {
      alarms: [{ name: 'HighCPU', state: 'OK', metric: 'CPUUtilization', threshold: 80 }],
      count: 1,
    },
    get_log_groups: {
      logGroups: [{ name: '/ecs/nci-oa-agent', storedBytes: 1024000, retentionDays: 30 }],
      count: 1,
    },
    // AWS CLI tools
    describe_instances: {
      instances: [
        {
          id: 'i-0abc123',
          name: 'nci-oa-agent-prod',
          state: 'running',
          type: 't3.medium',
          privateIp: '10.0.1.50',
        },
      ],
      count: 1,
    },
    describe_ecs_services: {
      services: [
        {
          name: 'nci-oa-agent',
          status: 'ACTIVE',
          runningCount: 2,
          desiredCount: 2,
          taskDefinition: 'nci-oa-agent:42',
        },
      ],
      count: 1,
    },
    list_lambda_functions: {
      functions: [
        { name: 'nci-oa-agent-processor', runtime: 'python3.12', memory: 256, timeout: 30 },
      ],
      count: 1,
    },
    describe_stack: {
      name: 'nci-oa-agent-prod',
      status: 'CREATE_COMPLETE',
      outputs: {
        ApiUrl: 'https://api.example.com',
        ClusterArn: 'arn:aws:ecs:us-east-1:123456789:cluster/prod',
      },
    },
    list_ecs_clusters: {
      clusters: [
        { name: 'nci-oa-agent-prod', runningTasks: 4, pendingTasks: 0, activeServices: 2 },
      ],
      count: 1,
    },
    get_caller_identity: {
      account: '123456789012',
      arn: 'arn:aws:iam::123456789012:user/developer',
      userId: 'AIDAEXAMPLE',
    },
    // Analyst tools
    run_sql: { rows: [{ count: 156 }], rowCount: 1 },
    export_csv: { filename: 'export_20260129.csv', rows: 100, size: '24KB' },
    analyze_data: { mean: 42.5, median: 40, stdDev: 8.3, count: 156 },
  };

  return mockResults[toolName] || { status: 'success', message: 'Operation completed' };
}

/**
 * Role-based agent access configuration.
 *
 * Defines which agent tabs each user role can access:
 * - developer: Full access to all agents (God mode)
 * - admin: Backend, AWS Admin for system management
 * - analyst: Data Analyst, AWS Admin for dashboards/monitoring
 * - co: Frontend (documents), Backend (workflow data)
 * - cor: Frontend (documents), Backend (workflow data)
 */
export const ROLE_AGENT_ACCESS: Record<UserRole, AgentType[]> = {
  developer: ['frontend', 'backend', 'aws_admin', 'analyst'], // Full access
  admin: ['backend', 'aws_admin'], // System management
  analyst: ['analyst', 'aws_admin'], // Data & monitoring
  co: ['frontend', 'backend'], // Document & workflow access
  cor: ['frontend', 'backend'], // Document & workflow access
};

/**
 * Get the agents accessible by a user role.
 */
export function getAgentsForRole(role: UserRole): AgentType[] {
  return ROLE_AGENT_ACCESS[role] || [];
}

/**
 * Check if a user role has access to a specific agent.
 */
export function canAccessAgent(role: UserRole, agentId: AgentType): boolean {
  const allowedAgents = ROLE_AGENT_ACCESS[role];
  return allowedAgents?.includes(agentId) ?? false;
}

/**
 * Get the default agent for a user role (first in their access list).
 */
export function getDefaultAgentForRole(role: UserRole): AgentType {
  const agents = getAgentsForRole(role);
  return agents[0] || 'frontend';
}
