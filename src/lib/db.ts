import { Db, MongoClient } from "mongodb";

declare global {
  var mongoClientPromise: Promise<MongoClient> | undefined;
}

function getMongoUri() {
  const uri = process.env.MONGODB_URI;
  if (!uri) throw new Error("MONGODB_URI غير مضبوط في ملف .env.");
  return uri;
}

export async function getDb(): Promise<Db> {
  if (!global.mongoClientPromise) {
    const client = new MongoClient(getMongoUri());
    global.mongoClientPromise = client.connect();
  }

  const client = await global.mongoClientPromise;
  return client.db(process.env.MONGODB_DB_NAME || "sard_ai");
}
