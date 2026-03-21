import type { MiniMax } from "./client.js";

/**
 * Base class for all API resources.
 *
 * Each resource holds a reference to the parent client, which provides
 * HTTP primitives (get, post, postStream, etc.) and configuration.
 */
export abstract class APIResource {
  protected _client: MiniMax;

  constructor(client: MiniMax) {
    this._client = client;
  }
}
