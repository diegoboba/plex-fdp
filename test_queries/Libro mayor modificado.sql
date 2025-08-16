-- Libro mayor modificado
-- Active: 1748873165894@@20.197.250.53@33010@onze_center
SELECT 
COALESCE(CC.IDEmpresa, 0) AS IDEmpresa, 
e.NombreFantasia AS Empresa, 
CC.idCuenta, 
CC.CodigoCuenta,
CC.Descripcion, 
A.FechaHora, 
A.Concepto,
s.NombreFantasia AS Sucursal, 
AD.Leyenda, 
AD.Debe, 
AD.Haber

FROM cuentascontables CC

LEFT JOIN asientos_detalle AD USING(idCuenta)
LEFT JOIN asientos A USING(idAsiento)
LEFT JOIN empresas e ON(cc.IDEmpresa=e.Empresa)
LEFT JOIN sucursales s ON(A.IdSucursalOrigen=s.Sucursal)

WHERE DATE(A.FechaHora) >= '2025-01-01'
    AND A.idEstadoAsiento <> 2 

ORDER BY idempresa,idcuenta,fechahora;