import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync } from 'fs';
import { join } from 'path';
import { database } from '../database.js';

const TEST_DB_DIR = join(process.cwd(), 'test_data');
const TEST_DB_FILE = join(TEST_DB_DIR, 'test_db.json');

describe('Database Module', () => {
  beforeEach(() => {
    if (existsSync(TEST_DB_DIR)) {
      rmSync(TEST_DB_DIR, { recursive: true, force: true });
    }
    mkdirSync(TEST_DB_DIR, { recursive: true });
    
    // Override the DB_FILE constant for testing
    // This is a bit of a hack since the database module uses its own constants
    // We'll just use the actual implementation paths
  });

  afterEach(() => {
    if (existsSync(TEST_DB_DIR)) {
      rmSync(TEST_DB_DIR, { recursive: true, force: true });
    }
  });

  describe('hashPassword', () => {
    it('should hash password with scrypt', () => {
      const hash = database.hashPassword('password123', 'test_salt');
      expect(hash).toBeDefined();
      expect(typeof hash).toBe('string');
      expect(hash.length).toBeGreaterThan(0);
    });

    it('should produce different hashes for different salts', () => {
      const hash1 = database.hashPassword('password123', 'salt1');
      const hash2 = database.hashPassword('password123', 'salt2');
      expect(hash1).not.toBe(hash2);
    });

    it('should produce same hash for same password and salt', () => {
      const hash1 = database.hashPassword('password123', 'test_salt');
      const hash2 = database.hashPassword('password123', 'test_salt');
      expect(hash1).toBe(hash2);
    });
  });

  describe('loadDb and saveDb', () => {
    it('should initialize default users and VPS', () => {
      database.loadDb();
      expect(database.db.users['usr_free_user']).toBeDefined();
      expect(database.db.users['usr_brittainjaden347']).toBeDefined();
      expect(database.db.vps['vps-free-01']).toBeDefined();
    });

    it('should persist data to file', () => {
      database.loadDb();
      database.db.users['test_user'] = {
        id: 'test_user',
        username: 'test',
        salt: 'salt',
        password_hash: 'hash',
        api_key: 'key',
        created_at: new Date().toISOString()
      };
      database.saveDb();

      const raw = readFileSync(join(process.cwd(), 'data', 'cloudvps_db.json'), 'utf8');
      const data = JSON.parse(raw);
      expect(data.users['test_user']).toBeDefined();
    });

    it('should load persisted data on reload', () => {
      database.loadDb();
      database.db.users['persist_user'] = {
        id: 'persist_user',
        username: 'persist',
        salt: 'salt',
        password_hash: 'hash',
        api_key: 'key',
        created_at: new Date().toISOString()
      };
      database.saveDb();

      // Create new database instance
      const db2 = { users: {}, vps: {}, bots: {}, services: {} };
      const originalDb = database.db;
      database.db = db2;
      database.loadDb();

      expect(database.db.users['persist_user']).toBeDefined();
      database.db = originalDb;
    });
  });

  describe('initVpsWorkspace', () => {
    it('should create workspace directory and package.json', () => {
      database.initVpsWorkspace('test-vps');
      const pkgPath = join(process.cwd(), 'vps_instances', 'test-vps', 'package.json');
      expect(existsSync(pkgPath)).toBe(true);

      const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
      expect(pkg.name).toBe('vps-test-vps');
    });

    it('should not overwrite existing package.json', () => {
      database.initVpsWorkspace('test-vps2');
      const pkgPath = join(process.cwd(), 'vps_instances', 'test-vps2', 'package.json');
      writeFileSync(pkgPath, JSON.stringify({ name: 'custom', version: '2.0.0' }), 'utf8');

      database.initVpsWorkspace('test-vps2');
      const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
      expect(pkg.name).toBe('custom');
      expect(pkg.version).toBe('2.0.0');
    });
  });
});