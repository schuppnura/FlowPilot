// JWT decoding utility for extracting claims (persona, etc.)

export function decodeJWT(token: string): Record<string, any> {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid JWT format');
    }

    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(decoded);
  } catch (error) {
    console.error('Failed to decode JWT:', error);
    return {};
  }
}

export function extractPersonas(token: string): string[] {
  const claims = decodeJWT(token);
  console.log('DEBUG: Available claims in token:', Object.keys(claims).sort());
  console.log('DEBUG: Full claims:', claims);
  
  const personaValue = claims.persona;
  console.log('DEBUG: Persona claim value:', personaValue, 'type:', typeof personaValue);

  if (!personaValue) {
    console.log('DEBUG: No persona claim found in token');
    return [];
  }

  let extractedPersonas: string[] = [];
  
  if (Array.isArray(personaValue)) {
    extractedPersonas = personaValue.filter((p: any) => typeof p === 'string' && p.length > 0);
    console.log('DEBUG: Extracted personas as array:', extractedPersonas);
  } else if (typeof personaValue === 'string' && personaValue.length > 0) {
    extractedPersonas = [personaValue];
    console.log('DEBUG: Extracted persona as string:', extractedPersonas);
  } else {
    console.log('DEBUG: Persona value is not in expected format:', personaValue);
  }

  console.log('DEBUG: Final extracted personas:', extractedPersonas);
  return extractedPersonas;
}
