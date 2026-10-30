export interface ActionRequest {
  action_type: string;
  object_id: string;
  expected_revision: number;
}
export type DriftStatus = "healthy" | "drift" | "invalid";
