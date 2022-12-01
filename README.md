# OWL-on-FHIR
![owl-on-fhir logo](https://github.com/joeflack4/owl-on-fhir/blob/master/docs/owl-on-fhir%20logo%20v2.png?raw=true "OWL on FHIR")

A light-weight Python-based non-minimalistic OWL to FHIR converter.

## Usage
TODO: Functional, but doesn't have a CLI, and has some major (albeit simple) outstanding issues.

## Alternative OWL to FHIR converters
### OAK
https://github.com/INCATools/ontology-access-kit/  
An ontology toolkit. Has a full-featured LinkML and Python based OWL to FHIR converter, and is likely to be well maintained.  

### FHIR-OWL
https://github.com/aehrc/fhir-owl  
Take a minimalistic approach. Can convert top-level CodeSystem properties, concepts, and also supports some predicates, such as synonyms. Uses Java `owl-api`.
