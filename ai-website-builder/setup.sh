#!/bin/bash
set -e

BASE_DIR="$(pwd)/ai-website-builder"
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

# Create directories
mkdir -p apps/api/prisma
mkdir -p apps/api/src/auth
mkdir -p apps/api/src/prisma
mkdir -p apps/api/src/tenants
mkdir -p apps/api/src/jobs
mkdir -p apps/api/src/wordpress
mkdir -p apps/api/src/ai
mkdir -p apps/api/src/sites
mkdir -p apps/api/src/billing
mkdir -p apps/web/src/app/login
mkdir -p apps/web/src/app/signup
mkdir -p apps/web/src/app/onboarding
mkdir -p apps/web/src/app/dashboard
mkdir -p "apps/web/src/app/editor/[siteId]"
mkdir -p apps/web/src/app/billing
mkdir -p apps/web/src/lib
mkdir -p apps/web/public
mkdir -p packages/shared/src

echo "Directories created."


# ============================================
# ROOT FILES
# ============================================

cat > package.json << 'FILEEOF'
{
  "name": "ai-website-builder",
  "version": "1.0.0",
  "private": true,
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "db:migrate": "cd apps/api && npx prisma migrate dev",
    "db:seed": "cd apps/api && npx prisma db seed",
    "db:studio": "cd apps/api && npx prisma studio",
    "docker:up": "docker-compose up -d",
    "docker:down": "docker-compose down",
    "docker:logs": "docker-compose logs -f"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.3.0"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}
FILEEOF

cat > turbo.json << 'FILEEOF'
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": ["**/.env.*local"],
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**", "!.next/cache/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "lint": {
      "dependsOn": ["^build"]
    }
  }
}
FILEEOF

cat > .gitignore << 'FILEEOF'
# Dependencies
node_modules/
.pnp
.pnp.js

# Build outputs
dist/
.next/
out/
build/

# Environment files
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Logs
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Editor
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Prisma
apps/api/prisma/*.db
apps/api/prisma/*.db-journal

# Turbo
.turbo/

# Testing
coverage/

# Misc
*.pem
.vercel
FILEEOF

echo "Root files written."


# ============================================
# DOCKER COMPOSE FILES
# ============================================

cat > docker-compose.yml << 'FILEEOF'
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: builder-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: builder
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis for BullMQ
  redis:
    image: redis:7-alpine
    container_name: builder-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # WordPress Multisite
  wordpress:
    image: wordpress:6-php8.2-apache
    container_name: builder-wordpress
    restart: unless-stopped
    depends_on:
      wordpress-db:
        condition: service_healthy
    environment:
      WORDPRESS_DB_HOST: wordpress-db:3306
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: wordpress
      WORDPRESS_DB_NAME: wordpress
      WORDPRESS_CONFIG_EXTRA: |
        define('WP_ALLOW_MULTISITE', true);
        define('MULTISITE', true);
        define('SUBDIRECTORY_INSTALL', true);
        define('DOMAIN_CURRENT_SITE', 'localhost');
        define('PATH_CURRENT_SITE', '/');
        define('SITE_ID_CURRENT_SITE', 1);
        define('BLOG_ID_CURRENT_SITE', 1);
    ports:
      - "8080:80"
    volumes:
      - wordpress_data:/var/www/html
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/wp-admin/install.php"]
      interval: 10s
      timeout: 5s
      retries: 5

  # WordPress Database (MySQL)
  wordpress-db:
    image: mysql:8.0
    container_name: builder-wordpress-db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wordpress
      MYSQL_PASSWORD: wordpress
    volumes:
      - wordpress_db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 5s
      retries: 5

  # WP-CLI for WordPress management
  wp-cli:
    image: wordpress:cli
    container_name: builder-wp-cli
    depends_on:
      wordpress:
        condition: service_healthy
    volumes:
      - wordpress_data:/var/www/html
    user: "33:33"  # www-data user
    entrypoint: ["tail", "-f", "/dev/null"]  # Keep container running

  # API Service (for production-like testing)
  api:
    build:
      context: ./apps/api
      dockerfile: Dockerfile
    container_name: builder-api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/builder?schema=public
      REDIS_HOST: redis
      REDIS_PORT: 6379
      JWT_SECRET: development-secret-change-in-production
      WP_MULTISITE_URL: http://wordpress
      WP_PATH: /var/www/html
      WP_CLI_PATH: wp
      FRONTEND_URL: http://localhost:3000
      NODE_ENV: development
      PORT: 4000
    ports:
      - "4000:4000"
    volumes:
      - wordpress_data:/var/www/html:ro

  # Web Service (for production-like testing)
  web:
    build:
      context: ./apps/web
      dockerfile: Dockerfile
    container_name: builder-web
    restart: unless-stopped
    depends_on:
      - api
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:4000
    ports:
      - "3000:3000"

volumes:
  postgres_data:
  redis_data:
  wordpress_data:
  wordpress_db_data:
FILEEOF

cat > docker-compose.dev.yml << 'FILEEOF'
version: '3.8'

# Simplified Docker Compose for local development
# Runs only the infrastructure services (postgres, redis, wordpress)
# Use `npm run dev` for the API and Web services

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: builder-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: builder
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis for BullMQ
  redis:
    image: redis:7-alpine
    container_name: builder-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # WordPress Multisite
  wordpress:
    image: wordpress:6-php8.2-apache
    container_name: builder-wordpress
    restart: unless-stopped
    depends_on:
      wordpress-db:
        condition: service_healthy
    environment:
      WORDPRESS_DB_HOST: wordpress-db:3306
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: wordpress
      WORDPRESS_DB_NAME: wordpress
      WORDPRESS_CONFIG_EXTRA: |
        define('WP_ALLOW_MULTISITE', true);
        define('MULTISITE', true);
        define('SUBDIRECTORY_INSTALL', true);
        define('DOMAIN_CURRENT_SITE', 'localhost');
        define('PATH_CURRENT_SITE', '/');
        define('SITE_ID_CURRENT_SITE', 1);
        define('BLOG_ID_CURRENT_SITE', 1);
    ports:
      - "8080:80"
    volumes:
      - wordpress_data:/var/www/html

  # WordPress Database (MySQL)
  wordpress-db:
    image: mysql:8.0
    container_name: builder-wordpress-db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wordpress
      MYSQL_PASSWORD: wordpress
    volumes:
      - wordpress_db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
  wordpress_data:
  wordpress_db_data:
FILEEOF

echo "Docker compose files written."


# ============================================
# PACKAGES/SHARED
# ============================================

cat > packages/shared/package.json << 'FILEEOF'
{
  "name": "@builder/shared",
  "version": "1.0.0",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch"
  },
  "devDependencies": {
    "typescript": "^5.3.0"
  }
}
FILEEOF

cat > packages/shared/tsconfig.json << 'FILEEOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "declaration": true,
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitThis": true,
    "alwaysStrict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": false,
    "inlineSourceMap": true,
    "inlineSources": true,
    "experimentalDecorators": true,
    "strictPropertyInitialization": false,
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
FILEEOF

cat > packages/shared/src/index.ts << 'FILEEOF'
// ============================================
// CORE TYPES
// ============================================

export type TenantRole = 'owner' | 'admin' | 'member';

export interface Tenant {
  id: string;
  name: string;
  logoUrl: string | null;
  primaryColor: string;
  createdAt: Date;
}

export interface User {
  id: string;
  email: string;
  createdAt: Date;
}

export interface Membership {
  userId: string;
  tenantId: string;
  role: TenantRole;
}

export type SiteStatus = 'provisioning' | 'generating' | 'draft' | 'published' | 'error';

export interface Site {
  id: string;
  tenantId: string;
  ownerUserId: string;
  name: string;
  status: SiteStatus;
  wpSiteId: number | null;
  wpAdminUrl: string | null;
  wpSiteUrl: string | null;
  currentVersionId: string | null;
  publishedVersionId: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface SiteVersion {
  id: string;
  siteId: string;
  versionNumber: number;
  pageJson: SiteContent;
  createdAt: Date;
}

export type JobType = 'provision' | 'generate' | 'publish' | 'rollback';
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Job {
  id: string;
  siteId: string;
  type: JobType;
  status: JobStatus;
  error: string | null;
  createdAt: Date;
  completedAt: Date | null;
}

export interface JobLog {
  id: string;
  jobId: string;
  message: string;
  createdAt: Date;
}

export type SubscriptionStatus = 'active' | 'canceled' | 'past_due' | 'trialing' | 'incomplete';

export interface StripeSubscription {
  id: string;
  userId: string;
  stripeCustomerId: string;
  stripeSubscriptionId: string;
  status: SubscriptionStatus;
  currentPeriodEnd: Date;
}

// ============================================
// PAGE SCHEMA - Platform Agnostic JSON
// ============================================

export type SectionType = 'hero' | 'about' | 'services' | 'testimonials' | 'contact' | 'footer';
export type BlockType = 'text' | 'image' | 'button' | 'list';

export interface TextProps {
  content: string;
  variant: 'h1' | 'h2' | 'h3' | 'body' | 'small';
}

export interface ImageProps {
  src: string;
  alt: string;
}

export interface ButtonProps {
  text: string;
  href: string;
  variant: 'primary' | 'secondary';
}

export interface ListItem {
  id: string;
  title: string;
  description: string;
  icon?: string;
}

export interface ListProps {
  items: ListItem[];
  layout: 'grid' | 'list';
}

export type BlockProps = TextProps | ImageProps | ButtonProps | ListProps;

export interface Block {
  id: string;
  type: BlockType;
  props: BlockProps;
}

export interface Section {
  id: string;
  type: SectionType;
  variant: 1 | 2 | 3;
  blocks: Block[];
}

export interface Page {
  title: string;
  slug: string;
  sections: Section[];
}

export interface SiteContent {
  pages: Page[];
  settings: SiteSettings;
}

export interface SiteSettings {
  businessName: string;
  industry: string;
  stylePreset: StylePreset;
  accentColor: string;
  primaryCta: PrimaryCta;
  contactEmail: string;
  contactPhone: string;
}

export type StylePreset = 'modern' | 'classic' | 'bold' | 'minimal' | 'playful' | 'professional';
export type PrimaryCta = 'call' | 'book' | 'quote';

// ============================================
// API REQUEST/RESPONSE TYPES
// ============================================

// Auth
export interface SignupRequest {
  email: string;
  password: string;
  tenantId?: string; // Optional - uses default tenant if not provided
}

export interface LoginRequest {
  email: string;
  password: string;
  tenantId?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
  tenant: Tenant;
}

export interface MeResponse {
  user: User;
  tenant: Tenant;
  membership: Membership;
  subscription: {
    status: SubscriptionStatus;
    currentPeriodEnd: Date;
  } | null;
}

// Sites
export interface CreateSiteRequest {
  settings: SiteSettings;
}

export interface CreateSiteResponse {
  site: Site;
  jobId: string;
}

export interface GenerateSiteRequest {
  sectionId?: string; // Optional - regenerate specific section
}

export interface GenerateSiteResponse {
  jobId: string;
}

export interface SaveDraftRequest {
  pages: Page[];
}

export interface SaveDraftResponse {
  version: SiteVersion;
}

export interface PublishResponse {
  jobId: string;
}

export interface RollbackRequest {
  versionId: string;
}

export interface RollbackResponse {
  jobId: string;
}

export interface SiteDetailResponse {
  site: Site;
  currentVersion: SiteVersion | null;
  versions: SiteVersion[];
  activeJob: Job | null;
}

// Billing
export interface BillingStatusResponse {
  hasSubscription: boolean;
  subscription: {
    status: SubscriptionStatus;
    currentPeriodEnd: Date;
  } | null;
}

export interface CreateCheckoutResponse {
  checkoutUrl: string;
}

export interface CreatePortalResponse {
  portalUrl: string;
}

// Jobs
export interface JobStatusResponse {
  job: Job;
  logs: JobLog[];
}

// ============================================
// ONBOARDING WIZARD TYPES
// ============================================

export interface WizardStep1 {
  businessName: string;
}

export interface WizardStep2 {
  industry: string;
}

export interface WizardStep3 {
  stylePreset: StylePreset;
}

export interface WizardStep4 {
  accentColor: string;
}

export interface WizardStep5 {
  primaryCta: PrimaryCta;
}

export interface WizardStep6 {
  contactEmail: string;
  contactPhone: string;
}

export type WizardData = WizardStep1 & WizardStep2 & WizardStep3 & WizardStep4 & WizardStep5 & WizardStep6;

// ============================================
// CONSTANTS
// ============================================

export const STYLE_PRESETS: { value: StylePreset; label: string; description: string }[] = [
  { value: 'modern', label: 'Modern', description: 'Clean lines, lots of whitespace' },
  { value: 'classic', label: 'Classic', description: 'Timeless, elegant design' },
  { value: 'bold', label: 'Bold', description: 'Strong colors, impactful' },
  { value: 'minimal', label: 'Minimal', description: 'Simple and focused' },
  { value: 'playful', label: 'Playful', description: 'Fun, vibrant energy' },
  { value: 'professional', label: 'Professional', description: 'Corporate, trustworthy' },
];

export const INDUSTRIES = [
  'Restaurant',
  'Retail',
  'Healthcare',
  'Real Estate',
  'Legal',
  'Consulting',
  'Fitness',
  'Beauty & Spa',
  'Photography',
  'Construction',
  'Technology',
  'Education',
  'Other',
];

export const PRIMARY_CTA_OPTIONS: { value: PrimaryCta; label: string }[] = [
  { value: 'call', label: 'Call Us' },
  { value: 'book', label: 'Book Appointment' },
  { value: 'quote', label: 'Get a Quote' },
];

export const SECTION_LIBRARY: { type: SectionType; name: string; description: string }[] = [
  { type: 'hero', name: 'Hero', description: 'Main banner with headline' },
  { type: 'about', name: 'About', description: 'About your business' },
  { type: 'services', name: 'Services', description: 'List your services' },
  { type: 'testimonials', name: 'Testimonials', description: 'Customer reviews' },
  { type: 'contact', name: 'Contact', description: 'Contact information' },
  { type: 'footer', name: 'Footer', description: 'Footer with links' },
];

export const DEFAULT_ACCENT_COLORS = [
  '#2563EB', // Blue
  '#DC2626', // Red
  '#16A34A', // Green
  '#9333EA', // Purple
  '#EA580C', // Orange
  '#0891B2', // Cyan
];

// ============================================
// HELPER FUNCTIONS
// ============================================

export function generateId(): string {
  return Math.random().toString(36).substring(2, 15);
}

export function createDefaultSection(type: SectionType, settings: SiteSettings): Section {
  const id = generateId();

  switch (type) {
    case 'hero':
      return {
        id,
        type: 'hero',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: `Welcome to ${settings.businessName}`, variant: 'h1' } as TextProps },
          { id: generateId(), type: 'text', props: { content: 'Your trusted partner for all your needs', variant: 'body' } as TextProps },
          { id: generateId(), type: 'button', props: { text: settings.primaryCta === 'call' ? 'Call Us Today' : settings.primaryCta === 'book' ? 'Book Now' : 'Get a Quote', href: '#contact', variant: 'primary' } as ButtonProps },
          { id: generateId(), type: 'image', props: { src: '/placeholder-hero.jpg', alt: 'Hero image' } as ImageProps },
        ],
      };
    case 'about':
      return {
        id,
        type: 'about',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'About Us', variant: 'h2' } as TextProps },
          { id: generateId(), type: 'text', props: { content: `${settings.businessName} has been serving the ${settings.industry} industry with dedication and excellence.`, variant: 'body' } as TextProps },
          { id: generateId(), type: 'image', props: { src: '/placeholder-about.jpg', alt: 'About us' } as ImageProps },
        ],
      };
    case 'services':
      return {
        id,
        type: 'services',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'Our Services', variant: 'h2' } as TextProps },
          { id: generateId(), type: 'list', props: { items: [
            { id: generateId(), title: 'Service 1', description: 'Description of service 1' },
            { id: generateId(), title: 'Service 2', description: 'Description of service 2' },
            { id: generateId(), title: 'Service 3', description: 'Description of service 3' },
          ], layout: 'grid' } as ListProps },
        ],
      };
    case 'testimonials':
      return {
        id,
        type: 'testimonials',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'What Our Clients Say', variant: 'h2' } as TextProps },
          { id: generateId(), type: 'list', props: { items: [
            { id: generateId(), title: 'John D.', description: 'Excellent service! Highly recommended.' },
            { id: generateId(), title: 'Sarah M.', description: 'Professional and reliable. Will use again.' },
          ], layout: 'list' } as ListProps },
        ],
      };
    case 'contact':
      return {
        id,
        type: 'contact',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'Contact Us', variant: 'h2' } as TextProps },
          { id: generateId(), type: 'text', props: { content: `Email: ${settings.contactEmail}`, variant: 'body' } as TextProps },
          { id: generateId(), type: 'text', props: { content: `Phone: ${settings.contactPhone}`, variant: 'body' } as TextProps },
          { id: generateId(), type: 'button', props: { text: settings.primaryCta === 'call' ? 'Call Now' : settings.primaryCta === 'book' ? 'Book Appointment' : 'Request Quote', href: `tel:${settings.contactPhone}`, variant: 'primary' } as ButtonProps },
        ],
      };
    case 'footer':
      return {
        id,
        type: 'footer',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: `© ${new Date().getFullYear()} ${settings.businessName}. All rights reserved.`, variant: 'small' } as TextProps },
        ],
      };
  }
}
FILEEOF

echo "Shared package written."


# ============================================
# API - CONFIG FILES
# ============================================

cat > apps/api/package.json << 'FILEEOF'
{
  "name": "@builder/api",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "build": "nest build",
    "dev": "nest start --watch",
    "start": "nest start",
    "start:prod": "node dist/main",
    "lint": "eslint \"{src,apps,libs,test}/**/*.ts\" --fix",
    "prisma:generate": "prisma generate",
    "prisma:migrate": "prisma migrate dev",
    "prisma:seed": "ts-node prisma/seed.ts"
  },
  "dependencies": {
    "@nestjs/common": "^10.3.0",
    "@nestjs/config": "^3.1.0",
    "@nestjs/core": "^10.3.0",
    "@nestjs/jwt": "^10.2.0",
    "@nestjs/passport": "^10.0.3",
    "@nestjs/platform-express": "^10.3.0",
    "@prisma/client": "^5.8.0",
    "@builder/shared": "1.0.0",
    "bcrypt": "^5.1.1",
    "bullmq": "^5.1.0",
    "class-transformer": "^0.5.1",
    "class-validator": "^0.14.0",
    "ioredis": "^5.3.2",
    "passport": "^0.7.0",
    "passport-jwt": "^4.0.1",
    "reflect-metadata": "^0.2.1",
    "rxjs": "^7.8.1",
    "stripe": "^14.12.0",
    "openai": "^4.24.0"
  },
  "devDependencies": {
    "@nestjs/cli": "^10.3.0",
    "@nestjs/schematics": "^10.1.0",
    "@types/bcrypt": "^5.0.2",
    "@types/express": "^4.17.21",
    "@types/node": "^20.10.0",
    "@types/passport-jwt": "^4.0.0",
    "prisma": "^5.8.0",
    "ts-node": "^10.9.2",
    "typescript": "^5.3.0"
  },
  "prisma": {
    "seed": "ts-node prisma/seed.ts"
  }
}
FILEEOF

cat > apps/api/tsconfig.json << 'FILEEOF'
{
  "compilerOptions": {
    "module": "commonjs",
    "declaration": true,
    "removeComments": true,
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true,
    "allowSyntheticDefaultImports": true,
    "target": "ES2021",
    "sourceMap": true,
    "outDir": "./dist",
    "baseUrl": "./",
    "incremental": true,
    "skipLibCheck": true,
    "strictNullChecks": true,
    "noImplicitAny": true,
    "strictBindCallApply": true,
    "forceConsistentCasingInFileNames": true,
    "noFallthroughCasesInSwitch": true,
    "esModuleInterop": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*", "prisma/**/*"],
  "exclude": ["node_modules", "dist"]
}
FILEEOF

cat > apps/api/nest-cli.json << 'FILEEOF'
{
  "$schema": "https://json.schemastore.org/nest-cli",
  "collection": "@nestjs/schematics",
  "sourceRoot": "src",
  "compilerOptions": {
    "deleteOutDir": true
  }
}
FILEEOF

cat > apps/api/.env.example << 'FILEEOF'
# Database
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/builder?schema=public"

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# JWT
JWT_SECRET=your-super-secret-jwt-key-change-in-production

# Stripe (required for billing - get from https://dashboard.stripe.com)
# TODO: Add your Stripe keys
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# OpenAI (optional - fallback content will be used if not set)
# TODO: Add your OpenAI key for AI content generation
OPENAI_API_KEY=sk-...

# WordPress Multisite
WP_MULTISITE_URL=http://localhost:8080
WP_PATH=/var/www/html
WP_CLI_PATH=wp

# Frontend URL (for Stripe redirects)
FRONTEND_URL=http://localhost:3000

# Environment
NODE_ENV=development
PORT=4000
FILEEOF

cat > apps/api/Dockerfile << 'FILEEOF'
# API Dockerfile
FROM node:20-alpine AS base

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app

# Copy package files
COPY package*.json ./
COPY prisma ./prisma/

RUN npm ci

# Build the application
FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npx prisma generate
RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production

# Copy built application
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/package.json ./package.json

EXPOSE 4000

CMD ["npm", "run", "start:prod"]
FILEEOF

echo "API config files written."


# ============================================
# API - PRISMA
# ============================================

cat > apps/api/prisma/schema.prisma << 'FILEEOF'
// Prisma schema for AI Website Builder MVP

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

// ============================================
// TENANTS & USERS
// ============================================

model Tenant {
  id           String   @id @default(cuid())
  name         String
  slug         String   @unique
  logoUrl      String?  @map("logo_url")
  primaryColor String   @default("#2563EB") @map("primary_color")
  createdAt    DateTime @default(now()) @map("created_at")
  updatedAt    DateTime @updatedAt @map("updated_at")

  memberships Membership[]
  sites       Site[]

  @@map("tenants")
}

model User {
  id           String   @id @default(cuid())
  email        String   @unique
  passwordHash String   @map("password_hash")
  createdAt    DateTime @default(now()) @map("created_at")
  updatedAt    DateTime @updatedAt @map("updated_at")

  memberships   Membership[]
  sites         Site[]
  subscriptions StripeSubscription[]

  @@map("users")
}

enum MembershipRole {
  owner
  admin
  member
}

model Membership {
  id        String         @id @default(cuid())
  userId    String         @map("user_id")
  tenantId  String         @map("tenant_id")
  role      MembershipRole @default(member)
  createdAt DateTime       @default(now()) @map("created_at")

  user   User   @relation(fields: [userId], references: [id], onDelete: Cascade)
  tenant Tenant @relation(fields: [tenantId], references: [id], onDelete: Cascade)

  @@unique([userId, tenantId])
  @@map("memberships")
}

// ============================================
// SITES & VERSIONS
// ============================================

enum SiteStatus {
  provisioning
  generating
  draft
  published
  error
}

model Site {
  id                 String     @id @default(cuid())
  tenantId           String     @map("tenant_id")
  ownerUserId        String     @map("owner_user_id")
  name               String
  status             SiteStatus @default(provisioning)
  wpSiteId           Int?       @map("wp_site_id")
  wpAdminUrl         String?    @map("wp_admin_url")
  wpSiteUrl          String?    @map("wp_site_url")
  currentVersionId   String?    @map("current_version_id")
  publishedVersionId String?    @map("published_version_id")
  createdAt          DateTime   @default(now()) @map("created_at")
  updatedAt          DateTime   @updatedAt @map("updated_at")

  tenant   Tenant        @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  owner    User          @relation(fields: [ownerUserId], references: [id], onDelete: Cascade)
  versions SiteVersion[]
  jobs     Job[]

  @@map("sites")
}

model SiteVersion {
  id            String   @id @default(cuid())
  siteId        String   @map("site_id")
  versionNumber Int      @map("version_number")
  pageJson      Json     @map("page_json")
  createdAt     DateTime @default(now()) @map("created_at")

  site Site @relation(fields: [siteId], references: [id], onDelete: Cascade)

  @@unique([siteId, versionNumber])
  @@map("site_versions")
}

// ============================================
// JOBS & LOGS
// ============================================

enum JobType {
  provision
  generate
  publish
  rollback
}

enum JobStatus {
  pending
  running
  completed
  failed
}

model Job {
  id          String    @id @default(cuid())
  siteId      String    @map("site_id")
  type        JobType
  status      JobStatus @default(pending)
  error       String?
  metadata    Json?
  createdAt   DateTime  @default(now()) @map("created_at")
  completedAt DateTime? @map("completed_at")

  site Site     @relation(fields: [siteId], references: [id], onDelete: Cascade)
  logs JobLog[]

  @@map("jobs")
}

model JobLog {
  id        String   @id @default(cuid())
  jobId     String   @map("job_id")
  message   String
  createdAt DateTime @default(now()) @map("created_at")

  job Job @relation(fields: [jobId], references: [id], onDelete: Cascade)

  @@map("job_logs")
}

// ============================================
// STRIPE BILLING
// ============================================

enum SubscriptionStatus {
  active
  canceled
  past_due
  trialing
  incomplete
}

model StripeSubscription {
  id                   String             @id @default(cuid())
  userId               String             @map("user_id")
  stripeCustomerId     String             @map("stripe_customer_id")
  stripeSubscriptionId String             @unique @map("stripe_subscription_id")
  status               SubscriptionStatus @default(incomplete)
  currentPeriodEnd     DateTime           @map("current_period_end")
  createdAt            DateTime           @default(now()) @map("created_at")
  updatedAt            DateTime           @updatedAt @map("updated_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@map("stripe_subscriptions")
}
FILEEOF

cat > apps/api/prisma/seed.ts << 'FILEEOF'
import { PrismaClient, MembershipRole } from '@prisma/client';
import * as bcrypt from 'bcrypt';

const prisma = new PrismaClient();

async function main() {
  console.log('Seeding database...');

  // Create default demo tenant
  const demoTenant = await prisma.tenant.upsert({
    where: { slug: 'demo' },
    update: {},
    create: {
      name: 'Demo Builder',
      slug: 'demo',
      logoUrl: null,
      primaryColor: '#2563EB',
    },
  });
  console.log('Created demo tenant:', demoTenant.id);

  // Create demo user
  const passwordHash = await bcrypt.hash('demo1234', 10);
  const demoUser = await prisma.user.upsert({
    where: { email: 'demo@example.com' },
    update: {},
    create: {
      email: 'demo@example.com',
      passwordHash,
    },
  });
  console.log('Created demo user:', demoUser.id);

  // Create membership
  await prisma.membership.upsert({
    where: {
      userId_tenantId: {
        userId: demoUser.id,
        tenantId: demoTenant.id,
      },
    },
    update: {},
    create: {
      userId: demoUser.id,
      tenantId: demoTenant.id,
      role: MembershipRole.owner,
    },
  });
  console.log('Created membership');

  // Create a second tenant for white-label demo
  const acmeTenant = await prisma.tenant.upsert({
    where: { slug: 'acme' },
    update: {},
    create: {
      name: 'ACME Web Builder',
      slug: 'acme',
      logoUrl: null,
      primaryColor: '#DC2626',
    },
  });
  console.log('Created ACME tenant:', acmeTenant.id);

  console.log('Seeding complete!');
  console.log('');
  console.log('Demo credentials:');
  console.log('  Email: demo@example.com');
  console.log('  Password: demo1234');
  console.log('  Tenant: demo (or acme for different branding)');
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
FILEEOF

echo "API Prisma files written."


# ============================================
# API - SRC FILES (main, app.module, prisma)
# ============================================

cat > apps/api/src/main.ts << 'FILEEOF'
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, {
    rawBody: true, // Required for Stripe webhooks
  });

  // Enable CORS for frontend
  app.enableCors({
    origin: process.env.FRONTEND_URL || 'http://localhost:3000',
    credentials: true,
  });

  // Global validation pipe
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      forbidNonWhitelisted: true,
    }),
  );

  // Global prefix
  app.setGlobalPrefix('api');

  const port = process.env.PORT || 4000;
  await app.listen(port);
  console.log(`API running on http://localhost:${port}`);
}
bootstrap();
FILEEOF

cat > apps/api/src/app.module.ts << 'FILEEOF'
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { PrismaModule } from './prisma/prisma.module';
import { AuthModule } from './auth/auth.module';
import { SitesModule } from './sites/sites.module';
import { BillingModule } from './billing/billing.module';
import { JobsModule } from './jobs/jobs.module';
import { TenantsModule } from './tenants/tenants.module';
import { WordPressModule } from './wordpress/wordpress.module';
import { AiModule } from './ai/ai.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    PrismaModule,
    AuthModule,
    TenantsModule,
    SitesModule,
    BillingModule,
    JobsModule,
    WordPressModule,
    AiModule,
  ],
})
export class AppModule {}
FILEEOF

cat > apps/api/src/prisma/prisma.module.ts << 'FILEEOF'
import { Global, Module } from '@nestjs/common';
import { PrismaService } from './prisma.service';

@Global()
@Module({
  providers: [PrismaService],
  exports: [PrismaService],
})
export class PrismaModule {}
FILEEOF

cat > apps/api/src/prisma/prisma.service.ts << 'FILEEOF'
import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
FILEEOF

echo "API main/prisma files written."


# ============================================
# API - AUTH MODULE
# ============================================

cat > apps/api/src/auth/auth.types.ts << 'FILEEOF'
import { Request } from 'express';

export interface AuthUser {
  userId: string;
  email: string;
  tenantId: string;
}

export interface AuthRequest extends Request {
  user: AuthUser;
}
FILEEOF

cat > apps/api/src/auth/auth.dto.ts << 'FILEEOF'
import { IsEmail, IsString, MinLength, IsOptional } from 'class-validator';

export class SignupDto {
  @IsEmail()
  email: string;

  @IsString()
  @MinLength(8)
  password: string;

  @IsString()
  @IsOptional()
  tenantSlug?: string;
}

export class LoginDto {
  @IsEmail()
  email: string;

  @IsString()
  password: string;

  @IsString()
  @IsOptional()
  tenantSlug?: string;
}
FILEEOF

cat > apps/api/src/auth/jwt-auth.guard.ts << 'FILEEOF'
import { Injectable } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';

@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {}
FILEEOF

cat > apps/api/src/auth/jwt.strategy.ts << 'FILEEOF'
import { Injectable, UnauthorizedException } from '@nestjs/common';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, Strategy } from 'passport-jwt';
import { ConfigService } from '@nestjs/config';
import { PrismaService } from '../prisma/prisma.service';

export interface JwtPayload {
  sub: string;
  email: string;
  tenantId: string;
}

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor(
    configService: ConfigService,
    private prisma: PrismaService,
  ) {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      secretOrKey: configService.get<string>('JWT_SECRET') || 'dev-secret-change-in-production',
    });
  }

  async validate(payload: JwtPayload) {
    const user = await this.prisma.user.findUnique({
      where: { id: payload.sub },
    });

    if (!user) {
      throw new UnauthorizedException('User not found');
    }

    return {
      userId: payload.sub,
      email: payload.email,
      tenantId: payload.tenantId,
    };
  }
}
FILEEOF

cat > apps/api/src/auth/auth.module.ts << 'FILEEOF'
import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { PassportModule } from '@nestjs/passport';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { AuthService } from './auth.service';
import { AuthController } from './auth.controller';
import { JwtStrategy } from './jwt.strategy';

@Module({
  imports: [
    PassportModule.register({ defaultStrategy: 'jwt' }),
    JwtModule.registerAsync({
      imports: [ConfigModule],
      useFactory: async (configService: ConfigService) => ({
        secret: configService.get<string>('JWT_SECRET') || 'dev-secret-change-in-production',
        signOptions: { expiresIn: '7d' },
      }),
      inject: [ConfigService],
    }),
  ],
  controllers: [AuthController],
  providers: [AuthService, JwtStrategy],
  exports: [AuthService, JwtModule],
})
export class AuthModule {}
FILEEOF

echo "API auth module files written."


cat > apps/api/src/auth/auth.service.ts << 'FILEEOF'
import { Injectable, UnauthorizedException, ConflictException, NotFoundException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { PrismaService } from '../prisma/prisma.service';
import { SignupDto, LoginDto } from './auth.dto';

@Injectable()
export class AuthService {
  constructor(
    private prisma: PrismaService,
    private jwtService: JwtService,
  ) {}

  async signup(dto: SignupDto) {
    // Check if user exists
    const existingUser = await this.prisma.user.findUnique({
      where: { email: dto.email },
    });

    if (existingUser) {
      throw new ConflictException('Email already registered');
    }

    // Get tenant (use default if not specified)
    const tenant = await this.prisma.tenant.findUnique({
      where: { slug: dto.tenantSlug || 'demo' },
    });

    if (!tenant) {
      throw new NotFoundException('Tenant not found');
    }

    // Hash password
    const passwordHash = await bcrypt.hash(dto.password, 10);

    // Create user and membership in transaction
    const user = await this.prisma.$transaction(async (tx) => {
      const newUser = await tx.user.create({
        data: {
          email: dto.email,
          passwordHash,
        },
      });

      await tx.membership.create({
        data: {
          userId: newUser.id,
          tenantId: tenant.id,
          role: 'member',
        },
      });

      return newUser;
    });

    // Generate token
    const token = this.jwtService.sign({
      sub: user.id,
      email: user.email,
      tenantId: tenant.id,
    });

    return {
      token,
      user: {
        id: user.id,
        email: user.email,
        createdAt: user.createdAt,
      },
      tenant: {
        id: tenant.id,
        name: tenant.name,
        logoUrl: tenant.logoUrl,
        primaryColor: tenant.primaryColor,
        createdAt: tenant.createdAt,
      },
    };
  }

  async login(dto: LoginDto) {
    // Find user
    const user = await this.prisma.user.findUnique({
      where: { email: dto.email },
    });

    if (!user) {
      throw new UnauthorizedException('Invalid credentials');
    }

    // Verify password
    const isValid = await bcrypt.compare(dto.password, user.passwordHash);
    if (!isValid) {
      throw new UnauthorizedException('Invalid credentials');
    }

    // Get tenant (use default if not specified)
    const tenantSlug = dto.tenantSlug || 'demo';
    const tenant = await this.prisma.tenant.findUnique({
      where: { slug: tenantSlug },
    });

    if (!tenant) {
      throw new NotFoundException('Tenant not found');
    }

    // Check membership
    const membership = await this.prisma.membership.findUnique({
      where: {
        userId_tenantId: {
          userId: user.id,
          tenantId: tenant.id,
        },
      },
    });

    if (!membership) {
      // Auto-create membership for demo purposes
      await this.prisma.membership.create({
        data: {
          userId: user.id,
          tenantId: tenant.id,
          role: 'member',
        },
      });
    }

    // Generate token
    const token = this.jwtService.sign({
      sub: user.id,
      email: user.email,
      tenantId: tenant.id,
    });

    return {
      token,
      user: {
        id: user.id,
        email: user.email,
        createdAt: user.createdAt,
      },
      tenant: {
        id: tenant.id,
        name: tenant.name,
        logoUrl: tenant.logoUrl,
        primaryColor: tenant.primaryColor,
        createdAt: tenant.createdAt,
      },
    };
  }

  async getMe(userId: string, tenantId: string) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
    });

    if (!user) {
      throw new NotFoundException('User not found');
    }

    const tenant = await this.prisma.tenant.findUnique({
      where: { id: tenantId },
    });

    if (!tenant) {
      throw new NotFoundException('Tenant not found');
    }

    const membership = await this.prisma.membership.findUnique({
      where: {
        userId_tenantId: {
          userId: user.id,
          tenantId: tenant.id,
        },
      },
    });

    if (!membership) {
      throw new NotFoundException('Membership not found');
    }

    // Get subscription
    const subscription = await this.prisma.stripeSubscription.findFirst({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
    });

    return {
      user: {
        id: user.id,
        email: user.email,
        createdAt: user.createdAt,
      },
      tenant: {
        id: tenant.id,
        name: tenant.name,
        logoUrl: tenant.logoUrl,
        primaryColor: tenant.primaryColor,
        createdAt: tenant.createdAt,
      },
      membership: {
        userId: membership.userId,
        tenantId: membership.tenantId,
        role: membership.role,
      },
      subscription: subscription
        ? {
            status: subscription.status,
            currentPeriodEnd: subscription.currentPeriodEnd,
          }
        : null,
    };
  }
}
FILEEOF

cat > apps/api/src/auth/auth.controller.ts << 'FILEEOF'
import { Controller, Post, Get, Body, UseGuards, Req } from '@nestjs/common';
import { AuthService } from './auth.service';
import { SignupDto, LoginDto } from './auth.dto';
import { JwtAuthGuard } from './jwt-auth.guard';
import { AuthRequest } from './auth.types';

@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  /**
   * POST /api/auth/signup
   *
   * Request:
   * {
   *   "email": "user@example.com",
   *   "password": "securePassword123",
   *   "tenantSlug": "demo" // optional, defaults to "demo"
   * }
   *
   * Response:
   * {
   *   "token": "eyJhbGciOiJIUzI1NiIs...",
   *   "user": { "id": "...", "email": "user@example.com", "createdAt": "..." },
   *   "tenant": { "id": "...", "name": "Demo Builder", "primaryColor": "#2563EB", ... }
   * }
   */
  @Post('signup')
  async signup(@Body() dto: SignupDto) {
    return this.authService.signup(dto);
  }

  /**
   * POST /api/auth/login
   *
   * Request:
   * {
   *   "email": "user@example.com",
   *   "password": "securePassword123",
   *   "tenantSlug": "demo" // optional
   * }
   *
   * Response:
   * {
   *   "token": "eyJhbGciOiJIUzI1NiIs...",
   *   "user": { ... },
   *   "tenant": { ... }
   * }
   */
  @Post('login')
  async login(@Body() dto: LoginDto) {
    return this.authService.login(dto);
  }

  /**
   * GET /api/auth/me
   *
   * Headers:
   * Authorization: Bearer <token>
   *
   * Response:
   * {
   *   "user": { "id": "...", "email": "...", "createdAt": "..." },
   *   "tenant": { "id": "...", "name": "...", "primaryColor": "...", ... },
   *   "membership": { "role": "member" },
   *   "subscription": { "status": "active", "currentPeriodEnd": "..." } | null
   * }
   */
  @Get('me')
  @UseGuards(JwtAuthGuard)
  async getMe(@Req() req: AuthRequest) {
    return this.authService.getMe(req.user.userId, req.user.tenantId);
  }
}
FILEEOF

echo "API auth service/controller written."

