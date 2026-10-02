# Excel format specification

The workbook contains exactly four sheets in this order:

1. `Derechos e impuestos`
2. `Nomenclatura`
3. `Restricciones`
4. `Cuotas`

## Styling

- blue header fill: `4472C4`
- white bold header text
- thin borders on header and data cells
- wrapped text where helpful
- frozen headers
- autofilter enabled
- text number format (`@`) for HS/code-like columns

## Sheet layouts

### Derechos e impuestos

`HS_Code`, `Status`, `Overall_Status`, `Código`, dynamic agreement columns, `Código adicional`, `Código de cuota`

### Nomenclatura

Top header merges `Unidades de medida` across two subcolumns:

- `Código`
- `Descripción`

### Restricciones

`HS_Code`, `Status`, `Overall_Status`, `Código`, `Descripción`, `Código adicional`, `Valor`, `Código de cuota`

### Cuotas

`HS_Code`, `Status`, `Overall_Status`, `TRATAMIENTO GENERAL`
